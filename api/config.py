from pathlib import Path

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LEGAL_AI_", extra="ignore")

    runtime_dir: Path = ROOT / ".runtime"
    database_url: str = ""
    corpus_path: Path = ROOT / "corpus" / "manifest.json"
    encryption_key: str = Field(default="", repr=False)
    allowed_origins: list[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]
    secure_cookies: bool = False
    session_hours: int = Field(default=24, ge=1, le=168)
    requests_per_minute: int = Field(default=120, ge=1)
    uploads_per_minute: int = Field(default=10, ge=1)
    sessions_per_minute: int = Field(default=20, ge=1)
    upload_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024, le=10 * 1024 * 1024)
    parse_timeout_seconds: float = Field(default=10, gt=0, le=30)
    context_tokens: int = Field(default=1800, ge=50, le=4000)
    offline_only: bool = True
    pinecone_host: str = ""
    pinecone_api_key: str = Field(default="", repr=False)
    pinecone_dimension: int = Field(default=384, ge=1)
    pinecone_embedding_model: str = "operator-must-configure"
    production: bool = False

    @model_validator(mode="after")
    def validate_mode(self):
        if not self.offline_only:
            raise ValueError("This release is offline-only; live execution is not enabled.")
        if self.production and (not self.secure_cookies or not self.encryption_key):
            raise ValueError("Production requires secure cookies and an operator-supplied encryption key.")
        if self.production and any(not origin.startswith("https://") for origin in self.allowed_origins):
            raise ValueError("Production origins require HTTPS.")
        if not self.database_url:
            self.database_url = "sqlite:///" + (self.runtime_dir / "legal-ai.db").as_posix()
        return self
