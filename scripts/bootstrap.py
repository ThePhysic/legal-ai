"""Generate project-owned ignored local configuration, never read user credentials."""
import argparse
import os
import secrets
from pathlib import Path

from cryptography.fernet import Fernet

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose", action="store_true", help="Include a local PostgreSQL URL for Docker Compose")
    args = parser.parse_args()
    target = ROOT / ".env"
    if target.exists():
        print("Existing .env preserved. No keys/passwords were overwritten.")
        return
    runtime = ROOT / ".runtime"
    runtime.mkdir(mode=0o700, exist_ok=True)
    key_file = runtime / ".encryption.key"
    if not key_file.exists() and any((runtime / name).exists() for name in ("objects", "legal-ai.db", ".key-check.enc")):
        raise SystemExit("Existing runtime data has no durable key. Restore the original key; no replacement was generated.")
    # Preserve the backend's existing durable key, if it has already been created.
    key = key_file.read_text().strip() if key_file.exists() else Fernet.generate_key().decode()
    Fernet(key.encode())
    if not key_file.exists():
        key_file.write_text(key, encoding="ascii")
        os.chmod(key_file, 0o600)
    password = secrets.token_urlsafe(32)
    entries = {"LEGAL_AI_OFFLINE_ONLY": "true", "LEGAL_AI_ENCRYPTION_KEY": key,
               "LEGAL_AI_DATABASE_PASSWORD": password}
    if args.compose:
        entries["LEGAL_AI_DATABASE_URL"] = f"postgresql+psycopg://legalai:{password}@postgres:5432/legalai"
    descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf8", newline="\n") as handle:
        handle.write("# Generated local-only secrets. Never commit or print this file.\n")
        handle.writelines(f"{name}={value}\n" for name, value in entries.items())
    print("Created ignored local .env and durable encryption key. Secret values were not printed.")


if __name__ == "__main__":
    main()
