import io
import zipfile

import pytest
from docx import Document as WordDocument
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from sqlalchemy import select

from api.models import Chunk, Document
from api.parsing import ParseError, parse_document
from api.service import BackendService
from api.tests.conftest import upload


def text_pdf(text="Tenant pays a security deposit of 1500 dollars."):
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject({NameObject("/Type"): NameObject("/Font"), NameObject("/Subtype"): NameObject("/Type1"), NameObject("/BaseFont"): NameObject("/Helvetica")})
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})})
    content = DecodedStreamObject()
    content.set_data(f"BT /F1 12 Tf 72 720 Td ({text}) Tj ET".encode())
    page[NameObject("/Contents")] = writer._add_object(content)
    out = io.BytesIO()
    writer.write(out)
    return out.getvalue()


def test_real_pdf_docx_text_parsing_and_literal_analysis(client):
    pdf = upload(client, text_pdf(), "lease.pdf")
    assert pdf["status"] == "ready"
    assert "security deposit" in pdf["sections"][0]["text"]
    assert pdf["sections"][0]["locator"] == "page-1"
    word = WordDocument()
    word.add_heading("Lease", 1)
    word.add_paragraph("Tenant Alice shall pay a security deposit of $1,500 on 2026-12-01.")
    table = word.add_table(rows=1, cols=2)
    table.cell(0, 0).text, table.cell(0, 1).text = "Landlord", "Bob"
    out = io.BytesIO()
    word.save(out)
    docx = upload(client, out.getvalue(), "lease.docx")
    assert docx["status"] == "ready"
    assert "Bob" in docx["sections"][0]["text"]
    analysis = client.post(f"/v1/documents/{docx['document_id']}/analysis", json={"question": "What security deposit is stated?"}).json()
    assert "$1,500" in analysis["summary"]
    assert any(item["text"] == "$1,500" for item in analysis["findings"])
    assert analysis["answer"]["status"] == "answered"
    assert analysis["comparison"]["passages"]
    assert "identity" in analysis["limitations"][-1]


@pytest.mark.parametrize(("filename", "raw"), [("bad.pdf", b"not pdf"), ("bad.docx", b"not zip"), ("bad.txt", b"\x00binary"), ("bad.exe", b"no")])
def test_bad_signatures_and_types_never_searchable(client, filename, raw):
    result = client.post("/v1/documents", files={"file": (filename, raw)})
    assert result.status_code == 422
    assert client.post("/v1/search", json={"question": "bad binary", "source_scope": "private"}).json()["passages"] == []


def test_scanned_encrypted_and_page_caps():
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ParseError, match="No selectable text"):
        parse_document("scan.pdf", out.getvalue())
    writer.encrypt("secret")
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ParseError, match="Encrypted"):
        parse_document("secret.pdf", out.getvalue())
    writer = PdfWriter()
    for _ in range(151):
        writer.add_blank_page(width=100, height=100)
    out = io.BytesIO()
    writer.write(out)
    with pytest.raises(ParseError, match="150-page"):
        parse_document("many.pdf", out.getvalue())


def test_zip_bomb_traversal_external_relationship_and_text_caps():
    for filename, payload, compression in [
        ("word/document.xml", b"x" * 300_000, zipfile.ZIP_DEFLATED),
        ("../escape", b"x", zipfile.ZIP_STORED),
        ("word/_rels/document.xml.rels", b'<Relationships><Relationship TargetMode="External" /></Relationships>', zipfile.ZIP_STORED),
    ]:
        out = io.BytesIO()
        with zipfile.ZipFile(out, "w", compression=compression) as archive:
            archive.writestr(filename, payload)
        with pytest.raises(ParseError):
            parse_document("unsafe.docx", out.getvalue())
    with pytest.raises(ParseError, match="text or section cap"):
        parse_document("long.txt", b"x" * 400_001)
    with pytest.raises(ParseError, match="time limit"):
        parse_document("normal.txt", b"ordinary content", timeout=0.00001)


@pytest.mark.parametrize("failed_stage", ["extracting", "chunking", "indexing", "verifying"])
def test_durable_failure_retry_idempotency_and_restart(app, client, failed_stage):
    service = app.state.service
    def fail(stage):
        if stage == failed_stage:
            raise OSError("injected failure")
    service.failure_hook = fail
    failed = upload(client)
    assert failed["status"] == "failed"
    assert client.post("/v1/search", json={"question": "security deposit", "source_scope": "private"}).json()["passages"] == []
    service.failure_hook = None
    recovered = client.post(f"/v1/documents/{failed['document_id']}/retry").json()
    assert recovered["status"] == "ready"
    duplicate = upload(client)
    assert duplicate["document_id"] == failed["document_id"]
    with service.db() as db:
        chunks = list(db.scalars(select(Chunk).where(Chunk.document_id == failed["document_id"])))
        assert len(chunks) == recovered["passage_count"]
    service.engine.dispose()
    restarted = BackendService(app.state.settings)
    assert restarted.document(client.get("/v1/session").json()["workspace_id"], failed["document_id"])["status"] == "ready"
    restarted.engine.dispose()


def test_interrupted_index_recovery_retries_without_duplicates(app, client):
    document = upload(client)
    with app.state.service.db.begin() as db:
        item = db.get(Document, document["document_id"])
        item.status, item.is_current = "indexing", False
    app.state.service.engine.dispose()
    restarted = BackendService(app.state.settings)
    workspace = client.get("/v1/session").json()["workspace_id"]
    assert restarted.document(workspace, document["document_id"])["status"] == "failed"
    assert restarted.process(workspace, document["document_id"])["status"] == "ready"
    restarted.engine.dispose()


def test_deletion_failure_revokes_search_sources_download_and_runs_immediately(app, client, monkeypatch):
    document = upload(client)
    identity = document["document_id"]
    run = client.post("/v1/research", json={"question": "security deposit", "source_scope": "private"}).json()
    real_delete = app.state.service.storage.delete
    def fail(*args):
        raise OSError("injected object outage")
    monkeypatch.setattr(app.state.service.storage, "delete", fail)
    result = client.delete(f"/v1/documents/{identity}").json()
    assert result["status"] == "deletion_pending"
    for path in [f"/v1/sources/{identity}", f"/v1/documents/{identity}/download", f"/v1/runs/{run['run_id']}"]:
        assert client.get(path).status_code == 404
    assert client.get(f"/v1/documents/{identity}").json()["sections"] == []
    assert client.post("/v1/search", json={"question": "security deposit", "source_scope": "private"}).json()["passages"] == []
    monkeypatch.setattr(app.state.service.storage, "delete", real_delete)
    assert client.delete(f"/v1/documents/{identity}").json()["status"] == "deleted"
    assert client.delete(f"/v1/documents/{identity}").json()["status"] == "deleted"


def test_replacement_keeps_old_until_new_verified_then_revokes(app, client):
    old = upload(client)
    old_id = old["document_id"]
    new_text = b"# Lease revision\nTenant Alice pays a security deposit of $900."
    def fail(stage):
        if stage == "verifying":
            raise OSError("index verification failure")
    app.state.service.failure_hook = fail
    replacement = upload(client, new_text, replace_document_id=old_id)
    assert replacement["status"] == "failed"
    assert client.get(f"/v1/sources/{old_id}").status_code == 200
    app.state.service.failure_hook = None
    fixed = client.post(f"/v1/documents/{replacement['document_id']}/retry").json()
    assert fixed["status"] == "ready"
    assert client.get(f"/v1/sources/{old_id}").status_code == 404
    result = client.post("/v1/search", json={"question": "security deposit", "source_scope": "private"}).json()
    assert {item["source_id"] for item in result["passages"]} == {replacement["document_id"]}
    assert not app.state.service.storage.path(client.get("/v1/session").json()["workspace_id"], old_id).exists()


def test_replacement_with_already_indexed_content_still_revokes_old(client):
    old = upload(client)
    existing = upload(client, b"Tenant has a security deposit of $900.", filename="second.txt")
    replaced = upload(client, b"Tenant has a security deposit of $900.", filename="second.txt", replace_document_id=old["document_id"])
    assert replaced["document_id"] == existing["document_id"]
    assert client.get(f"/v1/sources/{old['document_id']}").status_code == 404


def test_multipart_never_spools_private_plaintext_to_disk(client, monkeypatch):
    import tempfile

    def forbid_plaintext_spool(*args, **kwargs):
        raise AssertionError("Private upload was spooled to unencrypted temporary storage")
    monkeypatch.setattr(tempfile, "TemporaryFile", forbid_plaintext_spool)
    result = upload(client, b"private-canary " * 90_000)
    assert result["status"] == "failed"  # exceeds extracted-text cap, never searchable


def test_chunked_request_cap_applies_before_json_parser(client):
    response = client.post("/v1/search", content=iter([b"x" * 20_000, b"y" * 20_000]), headers={"Content-Type": "application/json"})
    assert response.status_code == 413
