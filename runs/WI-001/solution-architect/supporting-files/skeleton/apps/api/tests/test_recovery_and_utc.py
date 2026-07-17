import hashlib
import os
import uuid
from datetime import UTC, datetime, timedelta, timezone

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text, update

from littleduck_api.config import Settings
from littleduck_api.context import TokenBudget
from littleduck_api.db import Database
from littleduck_api.engine import DemoGenerationEngine
from littleduck_api.main import create_app
from littleduck_api.models import Generation, User, UserSession
from littleduck_api.repository import GenerationRepository, UserPrincipal
from littleduck_api.time import utc_iso


def _database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://littleduck_test:local-only@127.0.0.1:5432/littleduck_test",
    )


def _repository(database: Database) -> GenerationRepository:
    engine = DemoGenerationEngine()
    return GenerationRepository(
        database.sessions,
        token_budget=TokenBudget(8192, 1024, 256),
        count_tokens=engine.count_tokens,
    )


async def _prepare(database: Database) -> UserPrincipal:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    async with database.sessions() as session, session.begin():
        await session.execute(
            text(
                "TRUNCATE llm_calls, generations, messages, conversations, admin_sessions, "
                "admins, user_sessions, users RESTART IDENTITY CASCADE"
            )
        )
        session.add(User(id=user_id, phone="13300133000"))
        session.add(
            UserSession(
                id=session_id,
                user_id=user_id,
                token_hash=hashlib.sha256(b"recovery-session").hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
    return UserPrincipal(user_id=user_id, session_id=session_id)


@pytest.mark.asyncio
async def test_database_unavailable_does_not_abort_application_startup() -> None:
    settings = Settings(
        database_url=(
            "postgresql+psycopg://unavailable:unavailable@127.0.0.1:1/unavailable"
            "?connect_timeout=1"
        ),
        recovery_retry_seconds=0.01,
    )
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.get("/healthz")
            assert response.status_code == 503
            assert response.json()["status"] == "degraded"
            assert response.json()["database"] == "unavailable"


@pytest.mark.asyncio
async def test_recovery_cutoff_fails_only_pre_start_streams_and_is_idempotent() -> None:
    database = Database(_database_url())
    repository = _repository(database)
    try:
        principal = await _prepare(database)
        old = await repository.create_generation(
            principal=principal,
            client_request_id=uuid.uuid4(),
            content="旧进程请求",
            conversation_id=None,
        )
        new = await repository.create_generation(
            principal=principal,
            client_request_id=uuid.uuid4(),
            content="本进程请求",
            conversation_id=None,
        )
        cutoff = datetime.now(UTC)
        async with database.sessions() as session, session.begin():
            await session.execute(
                update(Generation)
                .where(Generation.id == old.generation_id)
                .values(created_at=cutoff - timedelta(minutes=1))
            )
            await session.execute(
                update(Generation)
                .where(Generation.id == new.generation_id)
                .values(created_at=cutoff + timedelta(seconds=1))
            )

        assert await repository.fail_interrupted_generations(cutoff) == 1
        assert await repository.fail_interrupted_generations(cutoff) == 0
        old_view = await repository.get_generation(old.generation_id, principal.user_id)
        new_view = await repository.get_generation(new.generation_id, principal.user_id)
        assert old_view["generation"]["status"] == "failed"
        assert old_view["generation"]["errorCode"] == "GENERATION_INTERRUPTED"
        assert new_view["generation"]["status"] == "streaming"
        await repository.finish(new.generation_id, "failed", error_code="GENERATION_INTERRUPTED")
    finally:
        await database.dispose()


@pytest.mark.asyncio
async def test_asia_shanghai_database_values_are_serialized_as_utc() -> None:
    database = Database(_database_url())
    repository = _repository(database)
    try:
        principal = await _prepare(database)
        created = await repository.create_generation(
            principal=principal,
            client_request_id=uuid.uuid4(),
            content="验证时区",
            conversation_id=None,
        )
        await repository.finish(created.generation_id, "completed")
        async with database.sessions() as session:
            await session.execute(text("SET TIME ZONE 'Asia/Shanghai'"))
            assert await session.scalar(text("SHOW TIME ZONE")) == "Asia/Shanghai"
            generation = await session.scalar(
                select(Generation).where(Generation.id == created.generation_id)
            )
            assert generation is not None
            view = await repository._view(session, generation)
        generation_view = view["generation"]
        message_view = view["assistantMessage"]
        assert isinstance(generation_view, dict)
        assert isinstance(message_view, dict)
        for key in ("startedAt", "createdAt", "updatedAt", "finishedAt"):
            assert str(generation_view[key]).endswith("Z")
        for key in ("createdAt", "updatedAt"):
            assert str(message_view[key]).endswith("Z")
    finally:
        await database.dispose()


def test_utc_iso_normalizes_non_utc_offsets() -> None:
    value = datetime(2026, 7, 17, 16, 0, tzinfo=timezone(timedelta(hours=8)))
    assert utc_iso(value) == "2026-07-17T08:00:00Z"
    with pytest.raises(ValueError):
        utc_iso(datetime(2026, 7, 17, 8, 0))
