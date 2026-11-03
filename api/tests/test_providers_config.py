import json

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError

from api.config import Settings
from api.main import create_app
from api.providers import ExistingPineconeAdapter, GroundedLLMAdapter, PineconeProfile, ProviderUnavailable
from api.storage import EncryptedStorage


def profile(**overrides):
    return PineconeProfile(**{"host": "https://prepared-index.svc.test.pinecone.io", "api_key": "offline-transport-test",
        "dimension": 3, "embedding_model": "operator-pinned-model", "embedding_revision": "revision-1", **overrides})


def test_actual_pinned_pinecone_sdk_http_transport_is_scoped_bounded_and_has_no_create(monkeypatch):
    seen = []
    def transport(request):
        body = json.loads(request.content or b"{}")
        seen.append((request.url.path, body, request.headers))
        assert request.headers["x-pinecone-api-version"] == "2026-07"
        assert request.extensions["timeout"]["read"] <= 5
        if request.url.path == "/query":
            return httpx.Response(200, json={"matches": [{"id": "doc:version:1", "score": 0.9,
                "metadata": {"source_id": "doc", "version": "version"}}], "namespace": body["namespace"]})
        if request.url.path == "/vectors/upsert":
            return httpx.Response(200, json={"upsertedCount": 1})
        if request.url.path == "/vectors/delete":
            return httpx.Response(200, json={})
        raise AssertionError("Unexpected control-plane/create operation: " + str(request.url))
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(transport))
    adapter = ExistingPineconeAdapter(profile(), enabled=True, call_budget=3)
    canonical = {"doc:version:1": {"source_id": "doc", "version": "version", "passage_id": "doc:version:1", "text": "secret"}}
    result = adapter.query([1, 0, 0], workspace_id="server-owned-workspace", jurisdiction="US-CA", allowed_passages=canonical)
    assert result[0]["text"] == "secret"
    adapter.upsert([{"id": "doc:version:1", "values": [1, 0, 0], "metadata": {"source_id": "doc", "version": "version", "jurisdiction": "US-CA", "current": True}}], workspace_id="server-owned-workspace")
    adapter.delete(["doc:version:1"], workspace_id="server-owned-workspace")
    assert len(seen) == 3
    assert all(body["namespace"] == adapter.namespace("server-owned-workspace") for _, body, _ in seen)
    assert "private-" in seen[0][1]["namespace"]
    assert {"scope": {"$eq": "private"}} in seen[0][1]["filter"]["$and"]
    assert {"current": {"$eq": True}} in seen[0][1]["filter"]["$and"]
    assert all("indexes" not in path for path, _, _ in seen)


def test_pinecone_rejects_wrong_dimension_stale_identity_and_outage(monkeypatch):
    def transport(request):
        return httpx.Response(200, json={"matches": [{"id": "missing", "score": 1, "metadata": {}}]})
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(transport))
    adapter = ExistingPineconeAdapter(profile(), enabled=True, call_budget=2)
    with pytest.raises(ValueError, match="dimension"):
        adapter.query([1, 0], workspace_id=None, jurisdiction="US-CA", allowed_passages={})
    with pytest.raises(ProviderUnavailable, match="unauthorized or stale"):
        adapter.query([1, 0, 0], workspace_id=None, jurisdiction="US-CA", allowed_passages={})
    def timeout(request):
        raise httpx.ReadTimeout("transport timeout", request=request)
    adapter._index._http._client._transport = httpx.MockTransport(timeout)
    with pytest.raises(ProviderUnavailable, match="no offline substitution"):
        adapter.query([1, 0, 0], workspace_id=None, jurisdiction="US-CA", allowed_passages={})


def test_actual_pinecone_transient_http_error_uses_one_budgeted_attempt(monkeypatch):
    requests = []
    def transport(request):
        requests.append(request)
        return httpx.Response(503, json={"message": "synthetic unavailable"})
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kwargs: httpx.MockTransport(transport))
    adapter = ExistingPineconeAdapter(profile(), enabled=True, call_budget=1)
    with pytest.raises(ProviderUnavailable, match="no offline substitution"):
        adapter.query([1, 0, 0], workspace_id=None, jurisdiction="US-CA", allowed_passages={})
    assert len(requests) == 1


def test_disabled_adapters_never_touch_transports_and_generation_validates_references():
    adapter = ExistingPineconeAdapter(profile())
    with pytest.raises(ProviderUnavailable, match="disabled"):
        adapter.query([1, 0, 0], workspace_id=None, jurisdiction="US-CA", allowed_passages={})
    with pytest.raises(ProviderUnavailable, match="budget"):
        ExistingPineconeAdapter(profile(), enabled=True).query([1, 0, 0], workspace_id=None, jurisdiction="US-CA", allowed_passages={})
    called = []
    def transport(**request):
        called.append(request)
        return {"answer": "Quoted evidence", "claims": [{"claim_id": "1", "text": "Quoted evidence",
            "source_ids": ["source"], "passage_ids": ["source:v1:1"]}]}
    disabled = GroundedLLMAdapter(transport)
    with pytest.raises(ProviderUnavailable, match="disabled"):
        disabled.generate("question", [])
    assert called == []
    live_mock = GroundedLLMAdapter(transport, enabled=True)
    passages = [{"passage_id": "source:v1:1", "source_id": "source", "version": "v1", "text": "Quoted evidence", "source": {"version": "v1"}}]
    result = live_mock.generate("question", passages)
    assert result["semantic_support"] == "not_assessed"
    assert result["claims"][0]["identity_validated"]
    assert called[0]["max_output_tokens"] == 1000 and called[0]["timeout"] == 10
    with pytest.raises(ProviderUnavailable, match="citation validation"):
        live_mock.generate("question", [])


def test_config_offline_production_and_key_loss_are_explicit(tmp_path):
    with pytest.raises(ValidationError, match="offline-only"):
        Settings(offline_only=False)
    with pytest.raises(ValidationError, match="Production requires"):
        Settings(production=True)
    with pytest.raises(ValidationError, match="HTTPS"):
        Settings(production=True, secure_cookies=True, encryption_key=Fernet.generate_key().decode())
    with pytest.raises(ValueError, match="HTTPS"):
        profile(host="http://example.invalid").validate()
    storage = EncryptedStorage(tmp_path / "storage")
    encrypted = storage.seal({"private": "value"})
    assert EncryptedStorage(tmp_path / "storage").open(encrypted) == {"private": "value"}
    (tmp_path / "storage" / ".encryption.key").unlink()
    with pytest.raises(RuntimeError, match="key missing"):
        EncryptedStorage(tmp_path / "storage")


def test_rate_limits_and_upload_request_caps(tmp_path, corpus):
    app = create_app(Settings(runtime_dir=tmp_path / "limited", corpus_path=corpus,
                              sessions_per_minute=1, requests_per_minute=2, upload_max_bytes=1024))
    with TestClient(app, headers={"Origin": "http://localhost:3000"}) as client:
        assert client.post("/v1/sessions", json={}).status_code == 201
        assert client.post("/v1/sessions", json={}).status_code == 429
        assert client.post("/v1/documents", files={"file": ("big.txt", b"x" * 1025)}).status_code == 413
        assert client.get("/v1/session").status_code == 200
        assert client.get("/v1/session").status_code == 429
    app.state.service.engine.dispose()
