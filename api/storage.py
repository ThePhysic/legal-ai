import json
import os
import re
import tempfile
from pathlib import Path

from cryptography.fernet import Fernet


class EncryptedStorage:
    """Opaque ID paths and authenticated encryption for objects AND private SQL payloads.

    The local key survives restarts in the ignored runtime directory. Losing it makes
    existing records unreadable; it is never regenerated if any encrypted data exists.
    """

    def __init__(self, root: Path, supplied_key: str = ""):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        key_path = root / ".encryption.key"
        if supplied_key:
            key = supplied_key.encode("ascii")
        elif key_path.exists():
            key = key_path.read_bytes()
        else:
            if (root / "objects").exists() or (root / "legal-ai.db").exists():
                raise RuntimeError("Encryption key missing; restore the runtime key before opening existing data.")
            key = Fernet.generate_key()
            try:
                fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "wb") as handle:
                    handle.write(key)
            except FileExistsError:
                key = key_path.read_bytes()
        self.fernet = Fernet(key)
        sentinel = root / ".key-check.enc"
        if sentinel.exists():
            try:
                if self.open(sentinel.read_bytes()) != {"schema": "legal-ai-runtime-v1"}:
                    raise ValueError("Invalid key sentinel")
            except Exception as exc:
                raise RuntimeError("Configured encryption key cannot open existing runtime data.") from exc
        else:
            sentinel.write_bytes(self.seal({"schema": "legal-ai-runtime-v1"}))
        (root / "objects").mkdir(exist_ok=True)

    def seal(self, value):
        return self.fernet.encrypt(json.dumps(value, ensure_ascii=False).encode("utf-8"))

    def open(self, value: bytes):
        return json.loads(self.fernet.decrypt(value))

    def path(self, workspace_id: str, document_id: str):
        if not all(re.fullmatch(r"[a-f0-9]{32,64}", item) for item in (workspace_id, document_id)):
            raise ValueError("Invalid object identity")
        return self.root / "objects" / workspace_id / (document_id + ".enc")

    def put(self, workspace_id, document_id, raw: bytes):
        path = self.path(workspace_id, document_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, temp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(self.fernet.encrypt(raw))
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp_path, path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def get(self, workspace_id, document_id):
        return self.fernet.decrypt(self.path(workspace_id, document_id).read_bytes())

    def delete(self, workspace_id, document_id):
        self.path(workspace_id, document_id).unlink(missing_ok=True)

    def probe(self):
        descriptor, path = tempfile.mkstemp(dir=self.root, prefix=".health-", suffix=".enc")
        try:
            value = self.fernet.encrypt(b"legal-ai-health-probe")
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(value)
                handle.flush()
                os.fsync(handle.fileno())
            if self.fernet.decrypt(Path(path).read_bytes()) != b"legal-ai-health-probe":
                raise RuntimeError("Encrypted storage probe failed")
        finally:
            Path(path).unlink(missing_ok=True)
