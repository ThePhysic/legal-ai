import pytest
from fastapi.testclient import TestClient

from api.main import COOKIE
from api.tests.conftest import ORIGIN, upload


def test_every_private_route_and_run_is_workspace_scoped(app, client):
    document = upload(client)
    assert document["status"] == "ready"
    identity = document["document_id"]
    researched = client.post("/v1/research", json={"question": "What security deposit is stated?", "source_scope": "private", "document_id": identity}).json()
    assert researched["status"] == "answered"
    with TestClient(app, headers={"Origin": ORIGIN}) as other:
        other.post("/v1/sessions", json={})
        for method, path, kwargs in [
            ("get", f"/v1/documents/{identity}", {}), ("get", f"/v1/documents/{identity}/download", {}),
            ("delete", f"/v1/documents/{identity}", {}), ("post", f"/v1/documents/{identity}/retry", {}),
            ("post", f"/v1/documents/{identity}/analysis", {"json": {}}),
            ("get", f"/v1/sources/{identity}", {}), ("get", f"/v1/runs/{researched['run_id']}", {}),
            ("post", "/v1/search", {"json": {"question": "deposit", "source_scope": "private", "document_id": identity}}),
        ]:
            result = getattr(other, method)(path, **kwargs)
            assert result.status_code == 404, (path, result.text)
            assert "Alice" not in result.text
        assert other.get("/v1/documents").json() == {"documents": []}
        result = other.post("/v1/search", json={"question": "Alice security deposit", "source_scope": "private"}).json()
        assert result["passages"] == []
    assert client.get(f"/v1/documents/{identity}/download").content.startswith(b"# Lease")


def test_auth_conflicts_revocation_and_origin(app, client):
    owner_token = client.cookies.get(COOKIE)
    with TestClient(app, headers={"Origin": ORIGIN}) as other:
        second = other.post("/v1/sessions", json={}).json()
    assert client.get("/v1/session", headers={"Authorization": "Bearer " + second["access_token"]}).status_code == 401
    assert client.get("/v1/session", headers={"Authorization": "Bearer " + owner_token}).status_code == 200
    assert client.post("/v1/search", json={"question": "deposit"}, headers={"Origin": "https://evil.invalid"}).status_code == 403
    with TestClient(app) as sdk:
        token = sdk.post("/v1/sessions", json={}).json()["access_token"]
        assert sdk.post("/v1/search", json={"question": "deposit"}).status_code == 403
        assert sdk.post("/v1/search", json={"question": "deposit"}, headers={"Authorization": "Bearer " + token}).status_code == 200
        assert sdk.post("/v1/sessions", json={}, headers={"Origin": "https://evil.invalid"}).status_code == 403
    assert client.delete("/v1/session").status_code == 204
    assert client.get("/v1/session", headers={"Authorization": "Bearer " + owner_token}).status_code == 401


@pytest.mark.parametrize("field", ["workspace_id", "namespace", "filter", "provider", "api_key"])
def test_client_cannot_supply_identity_or_provider(client, field):
    assert client.post("/v1/research", json={"question": "deposit", field: "spoof"}).status_code == 422


def test_absent_auth_and_diagnostics_are_protected(app):
    with TestClient(app) as client:
        for path in ["/v1/session", "/v1/documents", "/v1/sources/ca-1950.5", "/v1/runs/none", "/v1/evaluations"]:
            assert client.get(path).status_code == 401
        assert client.get("/health/live").json() == {"status": "ok"}
        ready = client.get("/health/ready").json()
        assert ready["providers"]["pinecone"] == "disabled_offline"
        assert "key" not in client.get("/health/ready").text


def test_private_bytes_sql_and_traces_encrypted(app, client):
    raw = b"TopSecretCanary7788 Tenant Alice pays a security deposit of $1500."
    document = upload(client, raw)
    identity = document["document_id"]
    answer = client.post("/v1/research", json={"question": "security deposit", "source_scope": "private"})
    assert answer.status_code == 200
    app.state.service.engine.dispose()
    for file in app.state.settings.runtime_dir.rglob("*"):
        if file.is_file():
            contents = file.read_bytes()
            assert b"TopSecretCanary7788" not in contents
            assert b"Tenant Alice" not in contents
    assert client.get(f"/v1/documents/{identity}").json()["sections"][0]["text"].startswith("TopSecretCanary7788")
    assert "no-store" in answer.headers["cache-control"]


def test_openapi_exposes_typed_responses_and_both_auth_methods(client):
    schema = client.get("/openapi.json").json()
    expected = {"Source", "Passage", "Claim", "SearchResponse", "ResearchResponse", "DocumentResponse", "AnalysisResponse", "EvaluationRun"}
    assert expected <= set(schema["components"]["schemas"])
    assert schema["paths"]["/v1/research"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"].endswith("ResearchResponse")
    assert schema["paths"]["/v1/research"]["post"]["security"] == [{"cookieSession": []}, {"bearerAuth": []}]
