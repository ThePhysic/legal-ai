import copy
import json
import socket
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.config import Settings
from api.main import create_app
from api.models import Run
from evaluations.datasets import load_dataset
from evaluations.service import EvaluationService


def test_real_offline_run_is_scoped_encrypted_and_reproducible(evaluation_fixture, monkeypatch):
    fixture = evaluation_fixture
    monkeypatch.setattr(socket, "create_connection", lambda *a, **k: pytest.fail("Network use during offline evaluation"))
    service = fixture["service"]
    first = service.create_run(fixture["owner"], "synthetic-test", ["lexical"])
    second = service.create_run(fixture["owner"], "synthetic-test", ["lexical"])
    assert first["freeze"]["dataset_sha256"] == second["freeze"]["dataset_sha256"]
    assert first["freeze"]["configuration_sha256"] == second["freeze"]["configuration_sha256"]
    metrics = first["configurations"][0]["metrics"]
    assert first["status"] == "completed"
    assert metrics["recall_at_10"] == metrics["mrr_at_10"] == 1
    assert metrics["answerable_count"] == 1 and metrics["expected_abstention_count"] == 1
    assert metrics["abstention"]["precision"] == metrics["abstention"]["recall"] == 1
    assert metrics["semantic_support"] is metrics["answer_correctness"] is None
    assert metrics["usage"]["provider_calls"] == metrics["usage"]["provider_cost_usd"] == 0
    assert metrics["search_latency_ms"]["p95"] >= metrics["search_latency_ms"]["p50"] >= 0
    assert service.get_run(fixture["owner"], first["evaluation_id"]) == first
    assert len(service.list_runs(fixture["owner"])["runs"]) == 2
    assert service.list_runs(fixture["other"])["runs"] == []
    with pytest.raises(HTTPException) as caught:
        service.get_run(fixture["other"], first["evaluation_id"])
    assert caught.value.status_code == 404
    with fixture["backend"].db() as db:
        record = db.scalar(select(Run).where(Run.id == first["evaluation_id"]))
        assert b"deadline to return" not in record.payload
        assert record.payload.startswith(b"gAAAA")
        assert record.workspace_id == fixture["owner"]


@pytest.mark.parametrize("configurations", [[], ["live"], ["lexical", "lexical"], ["lexical"] * 5])
def test_bounded_local_configurations(evaluation_fixture, configurations):
    with pytest.raises(HTTPException) as caught:
        evaluation_fixture["service"].create_run(evaluation_fixture["owner"], "synthetic-test", configurations)
    assert caught.value.status_code == 422


@pytest.mark.parametrize("defect", ["source_hash", "corpus_revision", "missing_passage", "private_source", "live_mode"])
def test_freeze_mismatch_fails_before_any_search(evaluation_fixture, monkeypatch, defect):
    fixture = evaluation_fixture
    backend = fixture["backend"]
    if defect == "source_hash":
        backend.sources["synthetic"]["content_hash"] = "b" * 64
    elif defect == "corpus_revision":
        backend.corpus_revision = "changed"
    elif defect == "missing_passage":
        backend.public_passages = backend.public_passages[1:]
    elif defect == "private_source":
        backend.public_passages[0]["source"]["scope"] = "private"
    else:
        backend.settings.offline_only = False
    monkeypatch.setattr(backend, "search_public", lambda **k: pytest.fail("Search must not begin before freeze validation"))
    with pytest.raises(HTTPException) as caught:
        fixture["service"].create_run(fixture["owner"], "synthetic-test", ["lexical"])
    assert caught.value.status_code == 409


def test_error_is_retained_scores_zero_and_does_not_leak_exception_text(evaluation_fixture, monkeypatch):
    fixture = evaluation_fixture
    def broken(**kwargs):
        raise RuntimeError("TENANT_PRIVATE_BANK_SECRET")
    monkeypatch.setattr(fixture["backend"], "search_public", broken)
    report = fixture["service"].create_run(fixture["owner"], "synthetic-test", ["lexical"])
    metrics = report["configurations"][0]["metrics"]
    assert report["status"] == "completed_with_errors"
    assert metrics["recall_at_10"] == metrics["mrr_at_10"] == 0
    assert metrics["error_count"] == 2
    assert metrics["usage"]["provider_calls"] is None
    assert metrics["usage"]["observed_provider_calls"] == 0
    assert "TENANT_PRIVATE_BANK_SECRET" not in json.dumps(report)


def test_frozen_config_drift_and_duplicate_results_are_visible(evaluation_fixture, monkeypatch):
    fixture = evaluation_fixture
    original = fixture["backend"].search_public
    def changed(**kwargs):
        response = original(**kwargs)
        response["trace"]["manifest"]["metric"] = "changed"
        if response["passages"]:
            response["passages"] *= 2
        return response
    monkeypatch.setattr(fixture["backend"], "search_public", changed)
    report = fixture["service"].create_run(fixture["owner"], "synthetic-test", ["lexical"])
    result = report["configurations"][0]
    assert result["manifest"]["metric"] == "cosine"
    assert result["metrics"]["failure_counts"]["configuration_changed_after_freeze"] == 2
    assert result["metrics"]["failure_counts"]["duplicate_search_identity"] == 1


def test_generated_private_text_and_fabricated_citations_never_enter_report(evaluation_fixture, monkeypatch):
    fixture = evaluation_fixture
    def malicious(*args, **kwargs):
        return {"status": "answered", "answer": "TENANT_PRIVATE_BANK_SECRET", "passages": [],
                "claims": [{"text": "TENANT_PRIVATE_BANK_SECRET", "passage_ids": ["foreign-private-id"],
                            "source_ids": ["other"], "identity_validated": True, "support_status": "verbatim_quote"}],
                "usage": {"provider_calls": 0, "provider_cost_usd": 0, "input_tokens": 0, "output_tokens": 0}}
    monkeypatch.setattr(fixture["backend"], "research", malicious)
    report = fixture["service"].create_run(fixture["owner"], "synthetic-test", ["lexical"])
    metrics = report["configurations"][0]["metrics"]
    assert metrics["citation_identity_rate"] == metrics["exact_quote_membership_rate"] == 0
    assert metrics["failure_counts"]["invalid_citation_identity"] == 2
    text = json.dumps(report)
    assert "TENANT_PRIVATE_BANK_SECRET" not in text
    assert "foreign-private-id" not in text


def test_invalid_dataset_path_and_inconsistent_labels_are_rejected(evaluation_fixture):
    fixture = evaluation_fixture
    with pytest.raises(ValueError):
        load_dataset("../other", fixture["directory"])
    dataset = copy.deepcopy(fixture["dataset"])
    dataset["cases"][0]["expected_abstain"] = True
    (fixture["directory"] / "synthetic-test.json").write_text(json.dumps(dataset))
    with pytest.raises(ValueError):
        load_dataset("synthetic-test", fixture["directory"])


@pytest.mark.parametrize("defect", ["duplicate_case_id", "noninteger_grade", "oversized_suite"])
def test_malformed_label_sets_are_rejected(evaluation_fixture, defect):
    fixture = evaluation_fixture
    dataset = copy.deepcopy(fixture["dataset"])
    if defect == "duplicate_case_id":
        dataset["cases"][1]["id"] = dataset["cases"][0]["id"]
    elif defect == "noninteger_grade":
        dataset["cases"][0]["judgments"]["synthetic:v1:return"] = True
    else:
        dataset["cases"] *= 51
    (fixture["directory"] / "synthetic-test.json").write_text(json.dumps(dataset))
    with pytest.raises(ValueError):
        load_dataset("synthetic-test", fixture["directory"])


def test_regular_and_private_runs_are_not_listed_as_evaluations(evaluation_fixture):
    fixture = evaluation_fixture
    identity = uuid.uuid4().hex
    fixture["backend"].store_run(fixture["owner"], {"run_id": identity, "question": "Private sample secret"}, private=True)
    assert fixture["service"].list_runs(fixture["owner"])["runs"] == []
    with pytest.raises(HTTPException) as caught:
        fixture["service"].get_run(fixture["owner"], identity)
    assert caught.value.status_code == 404


def test_invalid_usage_is_unknown_rather_than_claimed_free(evaluation_fixture, monkeypatch):
    fixture = evaluation_fixture
    original = fixture["backend"].search_public
    def unmeasured(**kwargs):
        response = original(**kwargs)
        response["usage"]["provider_calls"] = float("nan")
        response["usage"].pop("provider_cost_usd")
        return response
    monkeypatch.setattr(fixture["backend"], "search_public", unmeasured)
    report = fixture["service"].create_run(fixture["owner"], "synthetic-test", ["lexical"])
    metrics = report["configurations"][0]["metrics"]
    assert report["status"] == "completed_with_errors"
    assert metrics["usage"]["provider_calls"] is metrics["usage"]["provider_cost_usd"] is None
    assert metrics["usage"]["complete_observation_count"] == 2
    assert metrics["usage"]["total_observation_count"] == metrics["usage"]["expected_observation_count"] == 4
    assert metrics["failure_counts"]["usage_not_reported"] == 2
    assert "NaN" not in json.dumps(report)


def test_api_evaluations_authorize_server_workspace(evaluation_fixture, tmp_path):
    fixture = evaluation_fixture
    app = create_app(Settings(runtime_dir=tmp_path / "api-runtime", corpus_path=fixture["corpus_path"]))
    app.state.evaluation_service = EvaluationService(app.state.service, fixture["directory"])
    try:
        with TestClient(app, headers={"Origin": "http://localhost:3000"}) as client:
            assert client.get("/v1/evaluations").status_code == 401
            client.post("/v1/sessions", json={"label": "Evaluation owner"}).raise_for_status()
            response = client.post("/v1/evaluations", json={"dataset_id": "synthetic-test", "configurations": ["lexical"]})
            assert response.status_code == 201, response.text
            evaluation = response.json()
            assert evaluation["configurations"][0]["metrics"]["answerable_count"] == 1
            assert len(client.get("/v1/evaluations").json()["runs"]) == 1
            client.post("/v1/sessions", json={"label": "Other workspace"}).raise_for_status()
            assert client.get("/v1/evaluations").json()["runs"] == []
            assert client.get(f"/v1/evaluations/{evaluation['evaluation_id']}").status_code == 404
            spoof = client.post("/v1/evaluations", json={"dataset_id": "synthetic-test", "configurations": ["lexical"],
                                                        "workspace_id": fixture["owner"]})
            assert spoof.status_code == 422
    finally:
        app.state.service.engine.dispose()
