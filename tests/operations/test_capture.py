"""A changed publisher PDF must not reuse reviewed fixed page offsets."""
import hashlib
import json

import pytest

from scripts import capture_corpus


def test_capture_pin_matches_every_frozen_source():
    manifest = json.loads((capture_corpus.ROOT / "corpus/manifest.json").read_text(encoding="utf8"))
    assert {source["source_pdf_sha256"] for source in manifest["sources"]} == {capture_corpus.EXPECTED_PDF_SHA256}


def test_changed_pdf_is_rejected_before_parser_or_corpus_mutation(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    manifest = corpus / "manifest.json"
    manifest.write_bytes(b"preserve-reviewed-manifest")
    pdf = tmp_path / "updated.pdf"
    pdf.write_bytes(b"%PDF-1.7\nUnreviewed publisher revision")
    monkeypatch.setattr(capture_corpus, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["capture_corpus.py", "--pdf", str(pdf)])

    def forbidden_parser(*args, **kwargs):
        pytest.fail("An unreviewed PDF reached the fixed-page parser")

    monkeypatch.setattr(capture_corpus, "PdfReader", forbidden_parser)
    with pytest.raises(SystemExit, match="differs from the reviewed"):
        capture_corpus.main()
    assert manifest.read_bytes() == b"preserve-reviewed-manifest"
    assert not (corpus / "snapshots").exists()


def test_capture_checks_limit_and_identity(monkeypatch):
    raw = b"synthetic-reviewed-capture-bytes"
    monkeypatch.setattr(capture_corpus, "EXPECTED_PDF_SHA256", hashlib.sha256(raw).hexdigest())
    assert capture_corpus.validate_capture_bytes(raw) is raw
    with pytest.raises(SystemExit, match="capture limit"):
        capture_corpus.validate_capture_bytes(b"x" * (capture_corpus.MAX_PDF_BYTES + 1))
