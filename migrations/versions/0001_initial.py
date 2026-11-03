"""Initial encrypted workspace/document/run schema.

Revision ID: 0001
Revises:
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("workspaces", sa.Column("id", sa.String(64), primary_key=True),
                    sa.Column("label_cipher", sa.LargeBinary(), nullable=False), sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_table("sessions", sa.Column("token_hash", sa.String(64), primary_key=True),
                    sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspaces.id"), nullable=False),
                    sa.Column("expires_at", sa.DateTime(), nullable=False))
    op.create_index("ix_sessions_workspace_id", "sessions", ["workspace_id"])
    op.create_table("documents", sa.Column("id", sa.String(64), primary_key=True),
                    sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspaces.id"), nullable=False),
                    sa.Column("content_hash", sa.String(64), nullable=False), sa.Column("version", sa.String(80), nullable=False),
                    sa.Column("status", sa.String(24), nullable=False), sa.Column("is_current", sa.Boolean(), nullable=False),
                    sa.Column("replaced_id", sa.String(64), nullable=True), sa.Column("payload", sa.LargeBinary(), nullable=False),
                    sa.Column("created_at", sa.DateTime(), nullable=False), sa.Column("attempts", sa.Integer(), nullable=False),
                    sa.UniqueConstraint("workspace_id", "content_hash", name="uq_document_content"))
    op.create_index("ix_documents_workspace_id", "documents", ["workspace_id"])
    op.create_index("ix_documents_status", "documents", ["status"])
    op.create_table("chunks", sa.Column("id", sa.String(160), primary_key=True),
                    sa.Column("document_id", sa.String(64), sa.ForeignKey("documents.id"), nullable=False),
                    sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspaces.id"), nullable=False),
                    sa.Column("version", sa.String(80), nullable=False), sa.Column("payload", sa.LargeBinary(), nullable=False))
    op.create_index("ix_chunks_document_id", "chunks", ["document_id"])
    op.create_index("ix_chunks_workspace_id", "chunks", ["workspace_id"])
    op.create_table("runs", sa.Column("id", sa.String(64), primary_key=True),
                    sa.Column("workspace_id", sa.String(64), sa.ForeignKey("workspaces.id"), nullable=False),
                    sa.Column("private", sa.Boolean(), nullable=False), sa.Column("payload", sa.LargeBinary(), nullable=False),
                    sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_runs_workspace_id", "runs", ["workspace_id"])


def downgrade():
    for table in ("runs", "chunks", "documents", "sessions", "workspaces"):
        op.drop_table(table)
