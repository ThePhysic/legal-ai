"""Small deterministic tracked-file gate; complements dependency/CI scanning."""
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PATTERNS = [re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
            re.compile(rb"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
            re.compile(rb"\bsk-(?:proj-)?[A-Za-z0-9_-]{40,}\b"),
            re.compile(rb"\bAKIA[A-Z0-9]{16}\b")]
FORBIDDEN = {".env", "encryption.key", "legal-ai.db", "legal-ai.db-wal", "legal-ai.db-shm"}


def main():
    names = subprocess.check_output(["git", "ls-files", "-z"], cwd=ROOT).split(b"\0")
    failures = []
    for raw_name in names:
        if not raw_name:
            continue
        name = raw_name.decode("utf8")
        file = ROOT / name
        if not file.is_file():
            continue
        if file.name in FORBIDDEN or any(part in {".runtime", ".local", ".venv", "node_modules"} for part in file.parts):
            failures.append(name + ": forbidden runtime/dependency file")
            continue
        data = file.read_bytes()
        if any(pattern.search(data) for pattern in PATTERNS):
            failures.append(name + ": possible credential/private key")
    if failures:
        raise SystemExit("\n".join(failures))
    print("Tracked-file secret/runtime gate passed. This is not a guarantee of all secret formats.")


if __name__ == "__main__":
    main()
