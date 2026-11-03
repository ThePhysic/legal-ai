from cryptography.fernet import Fernet
import pytest

from scripts import bootstrap


@pytest.fixture
def project(tmp_path, monkeypatch):
    monkeypatch.setattr(bootstrap, "ROOT", tmp_path)
    monkeypatch.setattr("sys.argv", ["bootstrap.py"])
    return tmp_path


def test_new_configuration_is_valid_and_does_not_print_secrets(project, capsys):
    bootstrap.main()
    key = (project / ".runtime/.encryption.key").read_text().strip()
    Fernet(key.encode())
    assert "LEGAL_AI_OFFLINE_ONLY=true" in (project / ".env").read_text()
    assert key in (project / ".env").read_text()
    assert key not in capsys.readouterr().out


def test_existing_runtime_key_is_preserved(project):
    runtime = project / ".runtime"
    runtime.mkdir()
    key = Fernet.generate_key()
    (runtime / ".encryption.key").write_bytes(key)
    bootstrap.main()
    assert (runtime / ".encryption.key").read_bytes() == key
    assert key.decode() in (project / ".env").read_text()


def test_existing_private_state_without_key_is_not_rekeyed(project):
    runtime = project / ".runtime"
    runtime.mkdir()
    (runtime / "legal-ai.db").write_bytes(b"existing-state-canary")
    with pytest.raises(SystemExit, match="Restore the original key"):
        bootstrap.main()
    assert not (runtime / ".encryption.key").exists()
    assert not (project / ".env").exists()


def test_rerun_does_not_rotate_or_overwrite_local_configuration(project):
    bootstrap.main()
    key_before = (project / ".runtime/.encryption.key").read_bytes()
    env_before = (project / ".env").read_bytes()
    bootstrap.main()
    assert (project / ".runtime/.encryption.key").read_bytes() == key_before
    assert (project / ".env").read_bytes() == env_before
