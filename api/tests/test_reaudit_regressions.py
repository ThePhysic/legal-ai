"""Reproductions from the independent second audit, using synthetic text only."""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from api.models import Run
from api.storage import EncryptedStorage
from api.tests.conftest import ORIGIN, upload


@pytest.mark.parametrize("configuration", ["lexical", "dense", "hybrid", "rerank"])
@pytest.mark.parametrize("address", [
    "123 Main Street, Boston, Massachusetts",
    "123 Main Street, Boston, MA 02108",
    "123 Main Street, Berlin, Germany",
])
def test_quoted_foreign_postal_locations_cannot_be_masked(client, address, configuration):
    response = client.post("/v1/research", json={
        "question": f'When must the security deposit be returned for a rental at "{address}"?',
        "configuration": configuration,
    })
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "insufficient_evidence"
    assert not result["claims"] and not result["passages"]
    assert any("jurisdiction" in gap for gap in result["coverage_gaps"])


def test_explicit_california_wording_does_not_override_foreign_rental_address(client):
    result = client.post("/v1/research", json={
        "question": 'What California security deposit deductions apply at "123 Main Street, Boston, Massachusetts"?',
    }).json()
    assert result["status"] == "insufficient_evidence"


def test_date_after_quoted_street_is_not_discarded(client):
    result = client.post("/v1/research", json={
        "question": 'What deposit rules applied to "123 Main Street, California in 2020"?',
    }).json()
    assert result["status"] == "insufficient_evidence"
    assert any("Date-specific" in gap for gap in result["coverage_gaps"])


@pytest.mark.parametrize("text,expected_literal", [
    ("x" * 798 + "$1234 due deposit.", "$1234"),
    ("x" * 794 + "!2026-12-01 deposit date.", "2026-12-01"),
    ("word " * 135 + "y" * 200 + " deposit $500.", "$500"),
], ids=["split-amount", "split-date", "word-boundary-excerpt"])
def test_analysis_validates_only_actual_matching_passages(client, text, expected_literal):
    document = upload(client, text.encode(), "boundary.txt")
    passages = {passage["passage_id"]: passage for passage in document["passages"]}
    response = client.post(f"/v1/documents/{document['document_id']}/analysis", json={})
    assert response.status_code == 200
    findings = response.json()["findings"]
    literal = next(finding for finding in findings if finding["text"] == expected_literal)
    assert literal["locator"] == document["sections"][0]["locator"]
    for finding in findings:
        if finding["verified"] or finding["identity_validated"]:
            assert finding["support_status"] == "verbatim_quote"
            assert finding["passage_ids"]
            for identity in finding["passage_ids"]:
                passage = passages[identity]
                assert finding["text"] in passage["text"]
                assert passage["version"] == document["version"]
                assert passage["source"]["version"] == document["version"]
        elif finding["kind"] == "document_fact":
            assert finding["support_status"] == "not_assessed"
            assert finding["passage_ids"] == []
    if not any(expected_literal in passage["text"] for passage in passages.values()):
        assert not literal["verified"] and not literal["identity_validated"]


def test_deletion_purges_pasted_public_questions_and_legacy_history_only_for_owner(app, client):
    canary = "PrivateSecondAuditCanary deposit is $1500."
    document = upload(client, canary.encode())
    question = f'What security deposit rules relate to this text: "{canary}"?'
    research = client.post("/v1/research", json={"question": question}).json()
    searched = client.post("/v1/search", json={"question": question}).json()
    service = app.state.service
    with service.db.begin() as db:
        record = db.get(Run, research["run_id"])
        assert record.private is True
        workspace_id = record.workspace_id
        assert db.get(Run, searched["run_id"]).private is True
        # Simulate history created by the original release's public-scope flag.
        record.private = False
    safe_evaluation = uuid.uuid4().hex
    service.store_run(workspace_id, {"run_id": safe_evaluation, "run_kind": "evaluation"}, private=False)
    with TestClient(app, headers={"Origin": ORIGIN}) as other:
        assert other.post("/v1/sessions", json={"label": "Other"}).status_code == 201
        foreign_run = other.post("/v1/research", json={"question": "security deposit"}).json()["run_id"]
        assert client.delete(f"/v1/documents/{document['document_id']}").json()["status"] == "deleted"
        assert client.get(f"/v1/runs/{research['run_id']}").status_code == 404
        assert client.get(f"/v1/runs/{searched['run_id']}").status_code == 404
        assert service.run(workspace_id, safe_evaluation)["run_kind"] == "evaluation"
        assert other.get(f"/v1/runs/{foreign_run}").status_code == 200
    with service.db() as db:
        retained = list(db.scalars(select(Run).where(Run.workspace_id == workspace_id)))
        assert all(canary not in str(service.storage.open(record.payload)) for record in retained)


def test_missing_key_with_only_sentinel_does_not_create_a_replacement(tmp_path):
    storage = EncryptedStorage(tmp_path)
    sentinel = (tmp_path / ".key-check.enc").read_bytes()
    del storage
    (tmp_path / ".encryption.key").unlink()
    (tmp_path / "objects").rmdir()
    with pytest.raises(RuntimeError, match="Encryption key missing"):
        EncryptedStorage(tmp_path)
    assert not (tmp_path / ".encryption.key").exists()
    assert (tmp_path / ".key-check.enc").read_bytes() == sentinel
