from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def now():
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Workspace(Base):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    label_cipher: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class AuthSession(Base):
    __tablename__ = "sessions"
    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime)


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (UniqueConstraint("workspace_id", "content_hash", name="uq_document_content"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    content_hash: Mapped[str] = mapped_column(String(64))
    version: Mapped[str] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(24), default="uploaded", index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False)
    replaced_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    attempts: Mapped[int] = mapped_column(Integer, default=0)


class Chunk(Base):
    __tablename__ = "chunks"
    id: Mapped[str] = mapped_column(String(160), primary_key=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    version: Mapped[str] = mapped_column(String(80))
    payload: Mapped[bytes] = mapped_column(LargeBinary)


class Run(Base):
    __tablename__ = "runs"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    private: Mapped[bool] = mapped_column(Boolean, default=False)
    payload: Mapped[bytes] = mapped_column(LargeBinary)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
