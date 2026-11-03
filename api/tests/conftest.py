import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from api.config import Settings
from api.main import create_app

ORIGIN = "http://localhost:3000"


@pytest.fixture
def corpus(tmp_path):
    root = tmp_path / "corpus"
    root.mkdir()
    sections = [
        {"locator": "b", "title": "Security", "text": "A landlord may use a security deposit for unpaid rent, repair of damage and necessary cleaning. Security deposit deductions must be itemized.", "passage_id": "ca-1950.5:v1:b:1"},
        {"locator": "g", "title": "Return", "text": "Within 21 days after the tenant has vacated the premises, the landlord shall furnish an itemized statement and return the remaining security deposit.", "passage_id": "ca-1950.5:v1:g:1"},
    ]
    value = "\n\n".join(item["text"] for item in sections)
    (root / "deposit.txt").write_text(value, encoding="utf-8")
    raw = (root / "deposit.txt").read_bytes()
    source = {"source_id": "ca-1950.5", "title": "California Civil Code 1950.5 Security deposit", "publisher": "Synthetic test fixture",
              "url": "https://example.invalid/fixture", "source_type": "synthetic_test", "jurisdiction": "US-CA", "version": "v1",
              "content_hash": hashlib.sha256(raw).hexdigest(), "captured_at": "2026-11-03T00:00:00Z",
              "effective_from": None, "effective_to": None, "rights_basis": "Author-created synthetic testing text", "scope": "public",
              "file": "deposit.txt", "sections": sections}
    (root / "manifest.json").write_text(json.dumps({"revision": "test-v1", "sources": [source]}), encoding="utf-8")
    return root / "manifest.json"


@pytest.fixture
def app(tmp_path, corpus):
    app = create_app(Settings(runtime_dir=tmp_path / "runtime", corpus_path=corpus, requests_per_minute=1000))
    yield app
    app.state.service.engine.dispose()


@pytest.fixture
def client(app):
    with TestClient(app, headers={"Origin": ORIGIN}) as client:
        session = client.post("/v1/sessions", json={"label": "Owner"})
        assert session.status_code == 201
        yield client


def upload(client, text=b"# Lease\nTenant Alice shall pay a $1,500 security deposit. Deposit return is due on 2026-12-01.", filename="lease.txt", **extra):
    response = client.post("/v1/documents", files={"file": (filename, text)}, data=extra)
    assert response.status_code == 201, response.text
    return response.json()
