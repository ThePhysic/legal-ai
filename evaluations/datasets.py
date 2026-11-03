"""Strict loading of checked-in, public-only, versioned benchmark labels."""

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

DATASET_DIRECTORY = Path(__file__).with_name("datasets")
MAX_CASES = 100


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


@dataclass(frozen=True)
class Dataset:
    data: dict
    content_hash: str

    @property
    def cases(self):
        return self.data["cases"]

    def summary(self):
        return {"id": self.data["id"], "title": self.data["title"], "revision": self.data["revision"],
                "count": len(self.cases), "judgment_provenance": self.data["judgment_provenance"]}


def load_dataset(dataset_id: str, directory: Path = DATASET_DIRECTORY) -> Dataset:
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,79}", dataset_id):
        raise ValueError("Unknown public benchmark dataset.")
    path = directory / f"{dataset_id}.json"
    if not path.is_file():
        raise ValueError("Unknown public benchmark dataset.")
    raw = path.read_bytes()
    data = json.loads(raw)
    required = {"id", "title", "revision", "judgment_provenance", "corpus_revision", "sources", "cases"}
    if not required <= data.keys() or data["id"] != dataset_id:
        raise ValueError("Incomplete benchmark manifest.")
    if not isinstance(data["judgment_provenance"], str) or not data["judgment_provenance"].strip():
        raise ValueError("Benchmark judgment provenance is required.")
    if not 1 <= len(data["cases"]) <= MAX_CASES:
        raise ValueError("Benchmark case count exceeds the bounded public suite.")
    if not data["sources"] or len({item["source_id"] for item in data["sources"]}) != len(data["sources"]):
        raise ValueError("Benchmark requires unique frozen public sources.")
    for item in data["sources"]:
        if not item.get("version") or not re.fullmatch(r"[a-f0-9]{64}", item.get("content_hash", "")):
            raise ValueError("Benchmark source versions and SHA-256 hashes are required.")
    ids = set()
    for case in data["cases"]:
        required_case = {"id", "question", "category", "judgments", "expected_abstain", "jurisdiction", "applicable_on", "rationale"}
        if not required_case <= case.keys() or case["id"] in ids:
            raise ValueError("Benchmark cases require unique identities and explicit labels.")
        ids.add(case["id"])
        if not isinstance(case["question"], str) or not 1 <= len(case["question"].strip()) <= 2000:
            raise ValueError("Benchmark question length is invalid.")
        if type(case["expected_abstain"]) is not bool or not isinstance(case["judgments"], dict):
            raise ValueError("Benchmark abstention and passage judgments are invalid.")
        if any(type(grade) is not int or not 0 <= grade <= 3 for grade in case["judgments"].values()):
            raise ValueError("Benchmark relevance grades must be integers from zero to three.")
        positives = any(grade > 0 for grade in case["judgments"].values())
        if positives == case["expected_abstain"]:
            raise ValueError("Answerable cases need positive judgments; abstention cases cannot carry retrieval positives.")
        if not case["category"] or not case["rationale"]:
            raise ValueError("Every benchmark label requires a category and rationale.")
    return Dataset(data, hashlib.sha256(raw).hexdigest())


def list_datasets(directory: Path = DATASET_DIRECTORY) -> list[dict]:
    return [load_dataset(path.stem, directory).summary() for path in sorted(directory.glob("*.json"))]
