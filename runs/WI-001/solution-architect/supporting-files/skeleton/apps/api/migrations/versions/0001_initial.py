"""Create the LittleDuck MVP persistence boundary.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-17
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def timestamps() -> list[sa.Column[object]]:
    return [
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("phone", sa.String(length=20), nullable=False, unique=True),
        *timestamps(),
    )
    op.create_table(
        "admins",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("username", sa.String(length=64), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(length=255), nullable=False),
        *timestamps(),
    )
    op.create_table(
        "llm_configs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("api_key_ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("api_key_nonce", sa.LargeBinary(), nullable=False),
        *timestamps(),
        sa.CheckConstraint("id = 1", name="ck_llm_config_singleton"),
    )
    op.create_table(
        "user_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_user_sessions_user_id", "user_sessions", ["user_id"])
    op.create_table(
        "admin_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "admin_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admins.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(length=64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "conversations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(length=20), nullable=False),
        sa.Column("title_status", sa.String(length=16), nullable=False),
        sa.Column(
            "last_activity_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        *timestamps(),
        sa.CheckConstraint(
            "title_status IN ('temporary', 'final')", name="ck_conversation_title"
        ),
    )
    op.create_index(
        "ix_conversations_user_activity", "conversations", ["user_id", "last_activity_at"]
    )
    op.create_table(
        "messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column(
            "reply_to_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "retry_of_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
        ),
        *timestamps(),
        sa.CheckConstraint("role IN ('user', 'assistant')", name="ck_message_role"),
        sa.CheckConstraint(
            "status IN ('persisted', 'generating', 'completed', 'failed', 'stopped')",
            name="ck_message_status",
        ),
    )
    op.create_index(
        "ix_messages_conversation_created", "messages", ["conversation_id", "created_at"]
    )
    op.create_table(
        "generations",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "assistant_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("client_request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("stop_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("error_code", sa.String(length=64)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        *timestamps(),
        sa.UniqueConstraint(
            "user_id", "client_request_id", name="uq_generation_client_request"
        ),
        sa.CheckConstraint("kind IN ('chat', 'retry')", name="ck_generation_kind"),
        sa.CheckConstraint(
            "status IN ('streaming', 'completed', 'failed', 'stopped')",
            name="ck_generation_status",
        ),
    )
    op.create_index(
        "ix_generations_conversation_status", "generations", ["conversation_id", "status"]
    )
    op.create_index(
        "uq_generations_one_streaming_per_conversation",
        "generations",
        ["conversation_id"],
        unique=True,
        postgresql_where=sa.text("status = 'streaming'"),
    )
    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "conversation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("conversations.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "generation_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("generations.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "related_message_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("messages.id", ondelete="SET NULL"),
        ),
        sa.Column("call_type", sa.String(length=16), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model", sa.String(length=128), nullable=False),
        sa.Column("prompt", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_text", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_response_id", sa.String(length=255)),
        sa.Column("provider_error", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("generation_id", name="uq_llm_call_generation"),
        sa.CheckConstraint("call_type IN ('chat', 'title', 'retry')", name="ck_llm_call_type"),
        sa.CheckConstraint(
            "status IN ('in_progress', 'succeeded', 'failed', 'stopped')",
            name="ck_llm_call_status",
        ),
    )
    op.create_index(
        "ix_llm_calls_conversation_started", "llm_calls", ["conversation_id", "started_at"]
    )


def downgrade() -> None:
    op.drop_table("llm_calls")
    op.drop_table("generations")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("admin_sessions")
    op.drop_table("user_sessions")
    op.drop_table("llm_configs")
    op.drop_table("admins")
    op.drop_table("users")
