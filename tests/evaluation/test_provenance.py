import hashlib

import evaluations.service as service_module


def test_code_manifest_preserves_fingerprints_across_lf_and_crlf_checkouts(tmp_path, monkeypatch):
    source = '# A UTF-8 source comment: caf\u00e9\nVALUE = "deposit"\n'.encode("utf-8")
    # Use the actual manifest's source inventory, then emulate two checkouts.
    paths = list(service_module.code_manifest()["file_sha256"])
    monkeypatch.setattr(service_module, "ROOT", tmp_path)
    for relative in paths:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(source)
    lf = service_module.code_manifest()
    independently_expected = hashlib.sha256(source).hexdigest()
    assert set(lf["file_sha256"].values()) == {independently_expected}
    for relative in paths:
        (tmp_path / relative).write_bytes(source.replace(b"\n", b"\r\n"))
    crlf = service_module.code_manifest()
    assert crlf["file_sha256"] == lf["file_sha256"]
    assert "CRLF and CR newlines to LF" in crlf["source_hash_normalization"]
    assert "Dataset and corpus hashes remain raw-byte hashes" in crlf["source_hash_normalization"]
    # Normalization must not hide an actual source-content change.
    changed = tmp_path / paths[0]
    changed.write_bytes(source.replace(b"deposit", b"screening").replace(b"\n", b"\r\n"))
    assert service_module.code_manifest()["file_sha256"][paths[0]] != independently_expected


def test_bare_cr_source_newlines_share_the_lf_fingerprint(tmp_path):
    path = tmp_path / "source.py"
    path.write_bytes(b"x = 1\ry = 2\r")
    assert service_module.source_sha256(path) == hashlib.sha256(b"x = 1\ny = 2\n").hexdigest()
