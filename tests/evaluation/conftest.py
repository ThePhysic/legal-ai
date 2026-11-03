import hashlib
import json
import uuid

import pytest

from api.config import Settings
from api.models import Workspace
from api.service import BackendService
from evaluations.service import EvaluationService


@pytest.fixture
def evaluation_fixture(tmp_path):
    """Explicitly synthetic scorer/integration fixture; never shared authority."""
    root = tmp_path / "corpus"
    root.mkdir()
    sections = [
        {"passage_id": "synthetic:v1:return", "locator": "return", "title": "Return",
         "text": "A landlord shall return the remaining tenant security deposit within 21 days with an itemized statement."},
        {"passage_id": "synthetic:v1:clean", "locator": "clean", "title": "Cleaning",
         "text": "Security deposit cleaning deductions are limited to the reasonable cleaning costs of the premises."},
    ]
    raw = "\n\n".join(section["text"] for section in sections).encode()
    (root / "source.txt").write_bytes(raw)
    source = {"source_id": "synthetic", "title": "Synthetic tenant security deposit fixture", "publisher": "Test author",
              "url": "https://example.invalid/synthetic", "source_type": "synthetic_test", "jurisdiction": "US-CA",
              "scope": "public", "version": "v1", "content_hash": hashlib.sha256(raw).hexdigest(),
              "captured_at": "2026-11-03T00:00:00Z", "effective_from": None, "effective_to": None,
              "rights_basis": "Author-created test fixture only", "file": "source.txt", "sections": sections}
    corpus_path = root / "manifest.json"
    corpus_path.write_text(json.dumps({"revision": "synthetic-v1", "sources": [source]}))
    cases = [{"id": "return", "question": "What is the deadline to return a tenant security deposit with an itemized statement?",
              "category": "synthetic_positive", "judgments": {"synthetic:v1:return": 3}, "expected_abstain": False,
              "jurisdiction": "US-CA", "applicable_on": None, "rationale": "The author-created return paragraph states the deadline."},
             {"id": "foreign", "question": "What is the tenant security deposit return rule in Nevada?",
              "category": "jurisdiction_gap", "judgments": {}, "expected_abstain": True,
              "jurisdiction": "US-NV", "applicable_on": None, "rationale": "No synthetic Nevada source exists."}]
    dataset = {"id": "synthetic-test", "title": "Synthetic integration fixture", "revision": "test-1",
               "judgment_provenance": "Synthetic test author labels, not human relevance review.", "corpus_revision": "synthetic-v1",
               "sources": [{key: source[key] for key in ("source_id", "version", "content_hash")}], "cases": cases}
    directory = tmp_path / "datasets"
    directory.mkdir()
    (directory / "synthetic-test.json").write_text(json.dumps(dataset))
    backend = BackendService(Settings(runtime_dir=tmp_path / "runtime", corpus_path=corpus_path))
    owner, other = uuid.uuid4().hex, uuid.uuid4().hex
    with backend.db.begin() as db:
        for workspace in (owner, other):
            db.add(Workspace(id=workspace, label_cipher=backend.storage.seal("Test workspace")))
    yield {"backend": backend, "service": EvaluationService(backend, directory), "dataset": dataset,
           "directory": directory, "owner": owner, "other": other, "corpus_path": corpus_path}
    backend.engine.dispose()
