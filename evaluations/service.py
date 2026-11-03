"""Reproducible, bounded, offline evaluation of a frozen public corpus."""

import copy
import hashlib
import importlib.metadata
import math
import platform
import time
import uuid
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import select

from api.models import Run
from api.schemas import ResearchRequest
from evaluations.datasets import DATASET_DIRECTORY, digest, list_datasets, load_dataset
from evaluations.scoring import (
    abstention_scores,
    citation_scores,
    passage_identity_matches,
    percentile,
    retrieval_scores,
)

CONFIGURATIONS = ("lexical", "dense", "hybrid", "rerank")
RETRIEVAL_METRICS = ("recall_at_5", "recall_at_10", "mrr_at_10", "ndcg_at_10")
ROOT = Path(__file__).resolve().parents[1]
LIMITATIONS = [
    "Starter labels were authored by an implementation agent, not independently reviewed by legal experts or study participants.",
    "Passage relevance and abstention scores measure this frozen small benchmark; they do not establish legal correctness or comprehensive coverage.",
    "Citation identity and exact quote membership are mechanical checks, not independent semantic support judgments.",
    "Semantic support, answer correctness and human usability metrics are unassessed (null).",
    "Latencies are single-process local wall-clock observations, including attempted errors; no production/cloud latency claim is made.",
    "Observed provider usage is reported separately from unestimated local CPU and infrastructure costs.",
]


def now() -> str:
    return datetime.now(UTC).isoformat()


def mean(values):
    values = [value for value in values if value is not None]
    return sum(values) / len(values) if values else None


def code_manifest() -> dict:
    paths = ("api/service.py", "api/retrieval.py", "api/schemas.py", "evaluations/service.py",
             "evaluations/scoring.py", "evaluations/datasets.py")
    packages = {}
    for name in ("fastapi", "sqlalchemy", "pydantic", "cryptography"):
        try:
            packages[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            packages[name] = "not-installed"
    return {"python": platform.python_version(), "platform": platform.platform(), "packages": packages,
            "file_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in paths}}


class EvaluationService:
    def __init__(self, backend, dataset_directory: Path = DATASET_DIRECTORY):
        self.backend = backend
        self.dataset_directory = dataset_directory

    def list_runs(self, workspace_id):
        # Filter private runs before decrypting; never expose another workspace.
        with self.backend.db() as db:
            records = db.scalars(select(Run).where(Run.workspace_id == workspace_id, Run.private.is_(False))
                                 .order_by(Run.created_at.desc()))
            runs = []
            for record in records:
                payload = self.backend.storage.open(record.payload)
                if payload.get("run_kind") == "evaluation":
                    runs.append(self._public_run(payload))
        return {"runs": runs, "datasets": list_datasets(self.dataset_directory)}

    @staticmethod
    def _public_run(payload):
        return {key: value for key, value in payload.items() if key not in ("run_id", "run_kind")}

    def get_run(self, workspace_id, evaluation_id):
        payload = self.backend.run(workspace_id, evaluation_id)
        if payload.get("run_kind") != "evaluation":
            raise HTTPException(404, "Evaluation not found.")
        return self._public_run(payload)

    def _freeze(self, dataset, configurations):
        if self.backend.settings.offline_only is not True:
            raise HTTPException(409, "Evaluation requires the disabled-provider offline profile.")
        sources = [{key: source[key] for key in ("source_id", "version", "content_hash")}
                   for source in self.backend.sources.values()]
        sources.sort(key=lambda item: item["source_id"])
        expected = sorted(dataset.data["sources"], key=lambda item: item["source_id"])
        if sources != expected or dataset.data["corpus_revision"] != self.backend.corpus_revision:
            raise HTTPException(409, "The frozen benchmark corpus/version/hash does not match the loaded corpus.")
        canonical = copy.deepcopy({item["passage_id"]: item for item in self.backend.public_passages})
        if not canonical or len(canonical) != len(self.backend.public_passages):
            raise HTTPException(409, "The public corpus contains missing or duplicate passage identities.")
        if any(item["source"]["scope"] != "public" for item in canonical.values()):
            raise HTTPException(409, "Only public sources may enter a shared benchmark.")
        for case in dataset.cases:
            if any(identity not in canonical for identity in case["judgments"]):
                raise HTTPException(409, "Frozen passage judgments do not match the loaded public corpus.")
        frozen_configs = {name: copy.deepcopy(self.backend.evaluation_manifest(name, top_k=10)) for name in configurations}
        for name, manifest in frozen_configs.items():
            if manifest.get("mode") != "offline" or manifest.get("provider") != "local" or manifest.get("namespace") != "public-v1":
                raise HTTPException(409, "Only local public-corpus evaluation configurations are permitted.")
            if manifest.get("configuration") != name or manifest.get("top_k") != 10:
                raise HTTPException(409, "The evaluation configuration manifest is inconsistent.")
        identities = [{"passage_id": item["passage_id"], "source_id": item["source_id"], "version": item["version"],
                       "locator": item["locator"], "text_sha256": hashlib.sha256(item["text"].encode()).hexdigest()}
                      for item in sorted(canonical.values(), key=lambda item: item["passage_id"])]
        freeze = {"frozen_at": now(), "dataset_sha256": dataset.content_hash, "labels_sha256": digest(dataset.data),
                  "corpus_revision": self.backend.corpus_revision, "sources": sources, "passages": identities,
                  "corpus_identity_sha256": digest({"sources": sources, "passages": identities}),
                  "configuration_sha256": {name: digest(value) for name, value in frozen_configs.items()},
                  "execution": code_manifest(), "top_k": 10,
                  "measurement_plan": "Configuration order requested; stored case order; one search and one complete extractive research attempt per case; no warmup or retries.",
                  "metric_definitions": {
                      "recall_at_k": "Unique relevant IDs in first k ranks / all positive labeled IDs; macro-average over answerable cases, errors score zero.",
                      "mrr_at_10": "Reciprocal first relevant rank within 10, otherwise zero; macro-average over answerable cases.",
                      "ndcg_at_10": "DCG gains=(2^grade-1)/log2(rank+1); ideal descending positive grades; duplicate IDs gain once; unjudged gain zero.",
                      "abstention": "Positive=expected abstention; precision=TP/(TP+FP), recall=TP/(TP+FN); unavailable/errors excluded and counted.",
                      "latency": "perf_counter wall milliseconds; p50/p95 linearly interpolated sorted observations, inclusive endpoints.",
                  }}
        return freeze, frozen_configs, canonical

    def create_run(self, workspace_id, dataset_id, configurations):
        if not isinstance(configurations, list) or not 1 <= len(configurations) <= 4 or len(set(configurations)) != len(configurations) or any(name not in CONFIGURATIONS for name in configurations):
            raise HTTPException(422, "Choose one to four distinct local evaluation configurations.")
        try:
            dataset = load_dataset(dataset_id, self.dataset_directory)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(422, "Unknown or invalid frozen public benchmark.") from exc
        freeze, frozen_configs, canonical = self._freeze(dataset, configurations)
        run = {"evaluation_id": uuid.uuid4().hex, "dataset_id": dataset.data["id"],
               "dataset_revision": dataset.data["revision"], "created_at": freeze["frozen_at"],
               "status": "completed", "method": "Measured offline public retrieval and deterministic extractive research; no model/provider calls.",
               "judgment_provenance": dataset.data["judgment_provenance"], "freeze": freeze,
               "configurations": [], "limitations": LIMITATIONS}
        for name in configurations:
            cases = [self._measure_case(case, name, frozen_configs[name], canonical) for case in dataset.cases]
            metrics = self._aggregate(cases)
            run["configurations"].append({"configuration": name, "metrics": metrics,
                "manifest": {**frozen_configs[name], "configuration_sha256": freeze["configuration_sha256"][name],
                    "dataset_revision": dataset.data["revision"], "dataset_sha256": dataset.content_hash,
                    "generation_model": "none: deterministic exact quotations", "generation_model_version": "extractive-v1",
                    "provider_budget": {"calls": 0, "tokens": 0, "usd": 0},
                    "cost_basis": "Sum of observed local adapter usage; local CPU/infrastructure cost unestimated."},
                "cases": cases})
        if any(item["metrics"]["error_count"] for item in run["configurations"]):
            run["status"] = "completed_with_errors"
        # Backend owns the encrypted, server-scoped run storage. Cases contain
        # only frozen public questions, public IDs and safe mechanical results.
        self.backend.store_run(workspace_id, {**run, "run_id": run["evaluation_id"], "run_kind": "evaluation"}, private=False)
        return run

    def _measure_case(self, case, configuration, frozen_config, canonical):
        row = {"case_id": case["id"], "question": case["question"], "category": case["category"],
               "jurisdiction": case["jurisdiction"], "applicable_on": case["applicable_on"],
               "expected_abstain": case["expected_abstain"], "judgments": case["judgments"],
               "judgment_rationale": case["rationale"], "retrieved_passage_ids": [], "research_status": None,
               "actual_abstain": None, "citations": [], "errors": [], "failures": [], "usage_observations": []}
        arguments = {"question": case["question"], "configuration": configuration,
                     "jurisdiction": case["jurisdiction"], "applicable_on": case["applicable_on"], "top_k": 10}
        started = time.perf_counter()
        try:
            search = self.backend.search_public(**arguments)
            identities = [item["passage_id"] for item in search["passages"]]
            row["retrieved_passage_ids"] = [identity if identity in canonical else "[unrecognized]" for identity in identities]
            if any(identity not in canonical for identity in identities):
                row["failures"].append("nonpublic_or_unknown_search_identity")
            if any(item["passage_id"] in canonical and not passage_identity_matches(item, canonical[item["passage_id"]])
                   for item in search["passages"]):
                row["failures"].append("search_passage_identity_mismatch")
            if len(identities) != len(set(identities)):
                row["failures"].append("duplicate_search_identity")
            if search.get("trace", {}).get("manifest") != frozen_config:
                row["failures"].append("configuration_changed_after_freeze")
            self._usage(search, row)
        except Exception:
            # Exception text/tracebacks may contain source data or credentials.
            row["errors"].append("search_failed")
            row["retrieved_passage_ids"] = []
        finally:
            row["search_latency_ms"] = (time.perf_counter() - started) * 1000
        row["retrieval"] = retrieval_scores(row["retrieved_passage_ids"], case["judgments"])
        started = time.perf_counter()
        try:
            response = self.backend.research(ResearchRequest(**arguments, source_scope="public"), workspace_id=None, persist=False)
            status = response["status"]
            if status not in ("answered", "insufficient_evidence", "unavailable"):
                raise ValueError("Unknown research status")
            row["research_status"] = status
            row["actual_abstain"] = status == "insufficient_evidence" if status != "unavailable" else None
            if status == "unavailable":
                row["errors"].append("research_unavailable")
            row["citations"] = citation_scores(response, canonical)
            if status == "answered" and not row["citations"]:
                row["failures"].append("answered_without_citations")
            if any(not citation["identity_valid"] for citation in row["citations"]):
                row["failures"].append("invalid_citation_identity")
            if any(not citation["exact_quote_member"] for citation in row["citations"]):
                row["failures"].append("quote_not_in_frozen_passage")
            if status == "insufficient_evidence" and row["citations"]:
                row["failures"].append("abstention_with_claims")
            self._usage(response, row)
        except Exception:
            row["errors"].append("research_failed")
            row["actual_abstain"] = None
        finally:
            row["answer_latency_ms"] = (time.perf_counter() - started) * 1000
        if row["actual_abstain"] is not None and row["actual_abstain"] != case["expected_abstain"]:
            row["failures"].append("missed_abstention" if case["expected_abstain"] else "unexpected_abstention")
        if not case["expected_abstain"] and row["retrieval"]["recall_at_10"] < 1:
            row["failures"].append("incomplete_retrieval_at_10")
        row["passed"] = not row["errors"] and not row["failures"]
        return row

    @staticmethod
    def _usage(response, row):
        usage = response.get("usage", {})
        keys = ("provider_calls", "provider_cost_usd", "input_tokens", "output_tokens")
        safe = {}
        for key in keys:
            value = usage.get(key)
            safe[key] = value if type(value) in (int, float) and math.isfinite(value) and value >= 0 else None
        row["usage_observations"].append(safe)
        if any(value is None for value in safe.values()):
            row["errors"].append("usage_not_reported")
        if any(value is not None and value != 0 for value in safe.values()):
            row["failures"].append("offline_provider_budget_violation")

    @staticmethod
    def _aggregate(cases):
        answerable = [case for case in cases if not case["expected_abstain"]]
        retrieval = {key: mean([case["retrieval"][key] for case in answerable]) for key in RETRIEVAL_METRICS}
        observations = [item for case in cases for item in case["usage_observations"]]
        expected_observations = 2 * len(cases)
        usage = {}
        for key in ("provider_calls", "provider_cost_usd", "input_tokens", "output_tokens"):
            values = [item[key] for item in observations if item[key] is not None]
            usage[key] = sum(values) if len(values) == expected_observations else None
            usage[f"observed_{key}"] = sum(values)
        citations = [item for case in cases for item in case["citations"]]
        categories = {}
        for category in sorted({case["category"] for case in cases}):
            group = [case for case in cases if case["category"] == category]
            eligible = [case for case in group if not case["expected_abstain"]]
            categories[category] = {"count": len(group), "answerable_count": len(eligible),
                "expected_abstention_count": len(group) - len(eligible), "failed_count": sum(not case["passed"] for case in group),
                **{key: mean([case["retrieval"][key] for case in eligible]) for key in RETRIEVAL_METRICS}}
        return {**retrieval, "case_count": len(cases), "answerable_count": len(answerable),
            "expected_abstention_count": len(cases) - len(answerable),
            "error_count": sum(bool(case["errors"]) for case in cases),
            "error_event_count": sum(len(case["errors"]) for case in cases),
            "failed_case_count": sum(not case["passed"] for case in cases),
            "failure_case_ids": [case["case_id"] for case in cases if not case["passed"]],
            "failure_counts": dict(Counter(code for case in cases for code in case["failures"] + case["errors"])),
            "categories": categories,
            "search_latency_ms": {"p50": percentile([case["search_latency_ms"] for case in cases], .5),
                                  "p95": percentile([case["search_latency_ms"] for case in cases], .95), "count": len(cases)},
            "answer_latency_ms": {"p50": percentile([case["answer_latency_ms"] for case in cases], .5),
                                  "p95": percentile([case["answer_latency_ms"] for case in cases], .95), "count": len(cases)},
            "abstention": abstention_scores([(case["expected_abstain"], case["actual_abstain"]) for case in cases]),
            "citation_claim_count": len(citations),
            "citation_identity_rate": mean([int(item["identity_valid"]) for item in citations]),
            "exact_quote_membership_rate": mean([int(item["exact_quote_member"]) for item in citations]),
            "semantic_support": None, "answer_correctness": None, "human_usability": None,
            "usage": {**usage, "complete_observation_count": len(observations),
                      "expected_observation_count": expected_observations,
                      "cost_basis": "Observed provider usage only; local CPU/infrastructure cost unestimated."},
            "starter_retrieval_gate": {"recall_at_10_minimum": .70, "mrr_at_10_minimum": .60,
                "passed": bool(answerable and retrieval["recall_at_10"] >= .70 and retrieval["mrr_at_10"] >= .60)}}
