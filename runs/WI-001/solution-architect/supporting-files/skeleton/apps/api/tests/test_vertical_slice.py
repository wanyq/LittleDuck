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
from littleduck_api.context import conservative_token_estimate
from littleduck_api.engine import DemoGenerationEngine
from littleduck_api.main import create_app
from littleduck_api.models import Conversation, Generation, LlmCall, Message, User, UserSession
from littleduck_api.repository import UserPrincipal


class ControllableEngine:
    def __init__(self) -> None:
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(self, _: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "已生成的部分内容"
        self.waiting.set()
        await self.release.wait()
        yield "不应在停止后写入"

    def count_tokens(self, prompt: list[dict[str, str]]) -> int:
        return conservative_token_estimate(prompt)


class EmptyChunkEngine:
    async def stream(self, _: list[dict[str, str]]) -> AsyncIterator[str]:
        for chunk in ("", "a", "", "b"):
            yield chunk

    def count_tokens(self, prompt: list[dict[str, str]]) -> int:
        return conservative_token_estimate(prompt)


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


async def _reset(database: object) -> None:
    async with database.sessions() as session, session.begin():  # type: ignore[attr-defined]
        await session.execute(
            text(
                "TRUNCATE llm_calls, generations, messages, conversations, admin_sessions, "
                "admins, user_sessions, users RESTART IDENTITY CASCADE"
            )
        )


async def _add_user_session(database: object, raw_token: str, phone: str) -> UserPrincipal:
    user_id = uuid.uuid4()
    session_id = uuid.uuid4()
    async with database.sessions() as session, session.begin():  # type: ignore[attr-defined]
        session.add(User(id=user_id, phone=phone))
        session.add(
            UserSession(
                id=session_id,
                user_id=user_id,
                token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
                expires_at=datetime.now(UTC) + timedelta(days=7),
            )
        )
    return UserPrincipal(user_id=user_id, session_id=session_id)


@pytest.mark.asyncio
async def test_request_persistence_stream_terminal_and_ownership() -> None:
    app = create_app(Settings(database_url=_test_database_url()), DemoGenerationEngine())
    raw_session = "architecture-slice-user-session"
    other_session = "architecture-slice-other-session"

    async with app.router.lifespan_context(app):
        database = app.state.database
        await _reset(database)
        await _add_user_session(database, raw_session, "13800138000")
        await _add_user_session(database, other_session, "13900139000")

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            health = await client.get("/healthz")
            assert health.status_code == 200
            assert health.json()["database"] == "ok"
            assert health.json()["time"].endswith("Z")

            client.cookies.set("ld_user_session", raw_session)
            client_message_id = uuid.uuid4()
            payload = {"clientMessageId": str(client_message_id), "content": " 请验证纵向切片 "}
            rejected_origin = await client.post(
                "/api/v1/user/generations",
                json={**payload, "clientMessageId": str(uuid.uuid4())},
                headers={"origin": "https://untrusted.example"},
            )
            assert rejected_origin.status_code == 403

            streamed = await client.post("/api/v1/user/generations", json=payload)
            assert streamed.status_code == 200
            started = _event_data(streamed.text, "generation.started")
            deltas = _event_data(streamed.text, "generation.delta")
            completed = _event_data(streamed.text, "generation.completed")
            assert [event["sequence"] for event in deltas] == [2, 3, 4]
            assert len(started) == len(completed) == 1
            generation_id = started[0]["generationId"]
            assert isinstance(generation_id, str)

            terminal = await client.get(f"/api/v1/user/generations/{generation_id}")
            terminal_body = terminal.json()
            assert terminal_body["generation"]["status"] == "completed"
            assert terminal_body["generation"]["errorCode"] is None
            assert terminal_body["generation"]["finishedAt"].endswith("Z")
            assert terminal_body["assistantMessage"]["sequence"] == 2

            duplicate = await client.post("/api/v1/user/generations", json=payload)
            assert duplicate.status_code == 409
            assert duplicate.json()["error"]["generationId"] == generation_id

            client.cookies.set("ld_user_session", other_session)
            forbidden_as_not_found = await client.get(
                f"/api/v1/user/generations/{generation_id}"
            )
            assert forbidden_as_not_found.status_code == 404

        async with database.sessions() as session:
            call = await session.scalar(select(LlmCall))
            assert call is not None
            assert call.prompt[-1] == {"role": "user", "content": "请验证纵向切片"}
            assert call.input_tokens_estimated > 0
            messages = list(await session.scalars(select(Message).order_by(Message.sequence)))
            assert [message.sequence for message in messages] == [1, 2]
            assert messages[0].created_at == messages[1].created_at


@pytest.mark.asyncio
async def test_whitespace_validation_has_no_persistence_side_effects() -> None:
    app = create_app(Settings(database_url=_test_database_url()), DemoGenerationEngine())
    raw_session = "whitespace-validation-session"
    async with app.router.lifespan_context(app):
        database = app.state.database
        await _reset(database)
        await _add_user_session(database, raw_session, "13600136000")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.cookies.set("ld_user_session", raw_session)
            response = await client.post(
                "/api/v1/user/generations",
                json={"clientMessageId": str(uuid.uuid4()), "content": "   \t\n"},
            )
            assert response.status_code == 400
            assert response.json()["error"]["code"] == "VALIDATION_ERROR"
            too_long = await client.post(
                "/api/v1/user/generations",
                json={"clientMessageId": str(uuid.uuid4()), "content": f"  {'x' * 4001}  "},
            )
            assert too_long.status_code == 400
        async with database.sessions() as session:
            for model in (Conversation, Message, Generation, LlmCall):
                assert await session.scalar(select(func.count()).select_from(model)) == 0


@pytest.mark.asyncio
async def test_empty_engine_chunks_never_emit_empty_delta() -> None:
    app = create_app(Settings(database_url=_test_database_url()), EmptyChunkEngine())
    raw_session = "empty-chunk-session"
    async with app.router.lifespan_context(app):
        database = app.state.database
        await _reset(database)
        await _add_user_session(database, raw_session, "13500135000")
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            client.cookies.set("ld_user_session", raw_session)
            response = await client.post(
                "/api/v1/user/generations",
                json={"clientMessageId": str(uuid.uuid4()), "content": "测试空分片"},
            )
        deltas = _event_data(response.text, "generation.delta")
        assert [event["delta"] for event in deltas] == ["a", "b"]
        assert [event["sequence"] for event in deltas] == [2, 3]
        assert [event["accumulatedLength"] for event in deltas] == [1, 2]
        completed = _event_data(response.text, "generation.completed")
        assert completed[0]["assistantMessage"]["content"] == "ab"


@pytest.mark.asyncio
async def test_stop_persists_partial_content_and_emits_one_terminal_event() -> None:
    engine = ControllableEngine()
    app = create_app(Settings(database_url=_test_database_url()), engine)

    async with app.router.lifespan_context(app):
        database = app.state.database
        await _reset(database)
        principal = await _add_user_session(database, "stop-session", "13700137000")
        service = app.state.generation_service
        created, event_stream = await service.create(
            principal=principal,
            client_request_id=uuid.uuid4(),
            content="请停止这个回复",
            conversation_id=None,
        )
        iterator = event_stream.__aiter__()
        assert (await anext(iterator)).event_type == "generation.started"
        delta = await anext(iterator)
        assert delta.event_type == "generation.delta"
        await asyncio.wait_for(engine.waiting.wait(), timeout=1)

        accepted = await service.request_stop(created.generation_id, principal)
        assert accepted["generation"]["stopRequested"] is True
        engine.release.set()
        terminal = await asyncio.wait_for(anext(iterator), timeout=1)
        assert terminal.event_type == "generation.stopped"
        assert terminal.data["stoppedBy"] == "user"
        assert terminal.data["assistantMessage"]["content"] == "已生成的部分内容"
