import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import func, select, text

from littleduck_api.config import Settings
from littleduck_api.engine import DemoGenerationEngine
from littleduck_api.main import create_app
from littleduck_api.models import Generation, LlmCall, User, UserSession


class ControllableEngine:
    def __init__(self) -> None:
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(self, _: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "已生成的部分内容"
        self.waiting.set()
        await self.release.wait()
        yield "不应在停止后写入"


def _test_database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://littleduck_test:local-only@127.0.0.1:5432/littleduck_test",
    )


def _event_data(stream: str, event_type: str) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    for frame in stream.strip().split("\n\n"):
        lines = frame.splitlines()
        if f"event: {event_type}" not in lines:
            continue
        data_line = next(line for line in lines if line.startswith("data: "))
        value = json.loads(data_line.removeprefix("data: "))
        assert isinstance(value, dict)
        events.append(value)
    return events


@pytest.mark.asyncio
async def test_request_persistence_stream_terminal_and_ownership() -> None:
    settings = Settings(database_url=_test_database_url())
    app = create_app(settings, DemoGenerationEngine())
    raw_session = "architecture-slice-user-session"
    other_session = "architecture-slice-other-session"

    async with app.router.lifespan_context(app):
        database = app.state.database
        async with database.sessions() as session, session.begin():
            await session.execute(
                text(
                    "TRUNCATE llm_calls, generations, messages, conversations, "
                    "user_sessions, users RESTART IDENTITY CASCADE"
                )
            )
            user = User(id=uuid.uuid4(), phone="13800138000")
            other_user = User(id=uuid.uuid4(), phone="13900139000")
            session.add_all([user, other_user])
            await session.flush()
            expires_at = datetime.now(UTC) + timedelta(days=7)
            session.add_all(
                [
                    UserSession(
                        id=uuid.uuid4(),
                        user_id=user.id,
                        token_hash=hashlib.sha256(raw_session.encode()).hexdigest(),
                        expires_at=expires_at,
                    ),
                    UserSession(
                        id=uuid.uuid4(),
                        user_id=other_user.id,
                        token_hash=hashlib.sha256(other_session.encode()).hexdigest(),
                        expires_at=expires_at,
                    ),
                ]
            )

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/healthz")
            assert health.status_code == 200
            assert health.json()["database"] == "ok"

            client.cookies.set("ld_user_session", raw_session)
            client_message_id = uuid.uuid4()
            payload = {
                "clientMessageId": str(client_message_id),
                "content": "请验证纵向切片",
            }
            rejected_origin = await client.post(
                "/api/v1/user/generations",
                json={**payload, "clientMessageId": str(uuid.uuid4())},
                headers={"origin": "https://untrusted.example"},
            )
            assert rejected_origin.status_code == 403
            assert rejected_origin.json()["error"]["code"] == "FORBIDDEN"

            streamed = await client.post("/api/v1/user/generations", json=payload)
            assert streamed.status_code == 200
            assert streamed.headers["content-type"].startswith("text/event-stream")

            started = _event_data(streamed.text, "generation.started")
            deltas = _event_data(streamed.text, "generation.delta")
            completed = _event_data(streamed.text, "generation.completed")
            assert len(started) == 1
            assert len(deltas) == 3
            assert len(completed) == 1
            generation_id = started[0]["generationId"]
            assert isinstance(generation_id, str)

            terminal = await client.get(f"/api/v1/user/generations/{generation_id}")
            assert terminal.status_code == 200
            terminal_body = terminal.json()
            assert terminal_body["generation"]["status"] == "completed"
            assert terminal_body["assistantMessage"]["status"] == "completed"
            assert terminal_body["assistantMessage"]["content"].endswith("这是本地演示回复。")

            duplicate = await client.post("/api/v1/user/generations", json=payload)
            assert duplicate.status_code == 409
            assert duplicate.json()["error"]["code"] == "DUPLICATE_MESSAGE"
            assert duplicate.json()["error"]["generationId"] == generation_id

            client.cookies.set("ld_user_session", other_session)
            forbidden_as_not_found = await client.get(
                f"/api/v1/user/generations/{generation_id}"
            )
            assert forbidden_as_not_found.status_code == 404

        async with database.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(Generation)) == 1
            call = await session.scalar(select(LlmCall))
            assert call is not None
            assert call.status == "succeeded"
            assert call.prompt[-1] == {"role": "user", "content": "请验证纵向切片"}
            assert call.response_text.endswith("这是本地演示回复。")


@pytest.mark.asyncio
async def test_stop_persists_partial_content_and_emits_one_terminal_event() -> None:
    engine = ControllableEngine()
    app = create_app(Settings(database_url=_test_database_url()), engine)
    user_id = uuid.uuid4()

    async with app.router.lifespan_context(app):
        database = app.state.database
        async with database.sessions() as session, session.begin():
            await session.execute(
                text(
                    "TRUNCATE llm_calls, generations, messages, conversations, "
                    "user_sessions, users RESTART IDENTITY CASCADE"
                )
            )
            session.add(User(id=user_id, phone="13700137000"))

        service = app.state.generation_service
        created, event_stream = await service.create(
            user_id=user_id,
            client_request_id=uuid.uuid4(),
            content="请停止这个回复",
            conversation_id=None,
        )
        iterator = event_stream.__aiter__()
        assert (await anext(iterator)).event_type == "generation.started"
        delta = await anext(iterator)
        assert delta.event_type == "generation.delta"
        await asyncio.wait_for(engine.waiting.wait(), timeout=1)

        accepted = await service.request_stop(created.generation_id, user_id)
        assert accepted["generation"]["stopRequested"] is True
        engine.release.set()

        terminal = await asyncio.wait_for(anext(iterator), timeout=1)
        assert terminal.event_type == "generation.stopped"
        assert terminal.terminal is True
        assert terminal.data["generation"]["status"] == "stopped"
        assert terminal.data["assistantMessage"]["content"] == "已生成的部分内容"

        authoritative = await app.state.repository.get_generation(
            created.generation_id, user_id
        )
        assert authoritative["generation"]["status"] == "stopped"
        assert authoritative["assistantMessage"]["status"] == "stopped"

        async with database.sessions() as session:
            call = await session.scalar(
                select(LlmCall).where(LlmCall.generation_id == created.generation_id)
            )
            assert call is not None
            assert call.status == "stopped"
            assert call.response_text == "已生成的部分内容"
