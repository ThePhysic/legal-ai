"""Validate frozen source hashes and exact passages without network access."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def verify():
    folder = ROOT / "corpus"
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf8"))
    identities = set()
    for source in manifest["sources"]:
        file = (folder / source["file"]).resolve()
        assert file.is_relative_to(folder.resolve()), "Source path escapes corpus"
        content = file.read_text(encoding="utf8")
        assert hashlib.sha256(content.encode()).hexdigest() == source["content_hash"], source["source_id"]
        assert source["rights_basis"] and source["captured_at"] and source["version"]
        flattened = " ".join(content.split())
        for passage in source["sections"]:
            assert passage["passage_id"] not in identities, "Duplicate passage ID"
            identities.add(passage["passage_id"])
            assert source["version"] in passage["passage_id"]
            assert passage["text"] in flattened, "Passage absent from source"
            assert hashlib.sha256(passage["text"].encode()).hexdigest() == passage["content_hash"]
            assert len(passage["text"].encode()) <= 950
    print(json.dumps({"status": "verified", "revision": manifest["revision"], "sources": len(manifest["sources"]), "passages": len(identities)}))


if __name__ == "__main__":
    verify()
