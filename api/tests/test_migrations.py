import io

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from api.models import Base


def test_sqlite_upgrade_matches_models_and_roundtrip(tmp_path, monkeypatch):
    database = tmp_path / "migrations.db"
    monkeypatch.setenv("LEGAL_AI_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("LEGAL_AI_DATABASE_URL", "sqlite:///" + database.as_posix())
    config = Config("migrations/alembic.ini")
    command.upgrade(config, "head")
    engine = create_engine("sqlite:///" + database.as_posix())
    inspector = inspect(engine)
    assert set(Base.metadata.tables) <= set(inspector.get_table_names())
    for name, table in Base.metadata.tables.items():
        assert set(table.columns.keys()) == {column["name"] for column in inspector.get_columns(name)}
    engine.dispose()
    command.downgrade(config, "base")
    command.upgrade(config, "head")


def test_postgres_offline_ddl_renders_without_provider_or_database(tmp_path, monkeypatch):
    monkeypatch.setenv("LEGAL_AI_RUNTIME_DIR", str(tmp_path / "runtime"))
    monkeypatch.setenv("LEGAL_AI_DATABASE_URL", "postgresql+psycopg://local:local@localhost/legal_ai")
    output = io.StringIO()
    config = Config("migrations/alembic.ini", output_buffer=output)
    command.upgrade(config, "head", sql=True)
    ddl = output.getvalue()
    assert "CREATE TABLE documents" in ddl and "BYTEA" in ddl
    assert "uq_document_content" in ddl
