import asyncio
import hashlib
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import func, select, text, update

from littleduck_api.config import Settings
from littleduck_api.context import TokenBudget, conservative_token_estimate, select_complete_turns
from littleduck_api.main import create_app
from littleduck_api.models import Conversation, Generation, LlmCall, Message, User, UserSession
from littleduck_api.repository import InputBudgetExceededError, UserPrincipal


class TwoGenerationEngine:
    def __init__(self) -> None:
        self.waiting_count = 0
        self.both_waiting = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(self, _: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "部分"
        self.waiting_count += 1
        if self.waiting_count == 2:
            self.both_waiting.set()
        await self.release.wait()
        yield "完成"

    def count_tokens(self, prompt: list[dict[str, str]]) -> int:
        return conservative_token_estimate(prompt)


def _database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://littleduck_test:local-only@127.0.0.1:5432/littleduck_test",
    )


async def _reset(database: object) -> None:
    async with database.sessions() as session, session.begin():  # type: ignore[attr-defined]
        await session.execute(
            text(
                "TRUNCATE llm_calls, generations, messages, conversations, admin_sessions, "
                "admins, user_sessions, users RESTART IDENTITY CASCADE"
            )
        )


async def _same_user_principals(database: object) -> tuple[UserPrincipal, UserPrincipal]:
    user_id = uuid.uuid4()
    first_session = uuid.uuid4()
    second_session = uuid.uuid4()
    expires_at = datetime.now(UTC) + timedelta(days=7)
    async with database.sessions() as session, session.begin():  # type: ignore[attr-defined]
        session.add(User(id=user_id, phone="13400134000"))
        session.add_all(
            [
                UserSession(
                    id=first_session,
                    user_id=user_id,
                    token_hash=hashlib.sha256(b"session-a").hexdigest(),
                    expires_at=expires_at,
                ),
                UserSession(
                    id=second_session,
                    user_id=user_id,
                    token_hash=hashlib.sha256(b"session-b").hexdigest(),
                    expires_at=expires_at,
                ),
            ]
        )
    return (
        UserPrincipal(user_id=user_id, session_id=first_session),
        UserPrincipal(user_id=user_id, session_id=second_session),
    )


async def _next_terminal(iterator: AsyncIterator[object]) -> object:
    while True:
        event = await anext(iterator)
        if event.terminal:  # type: ignore[attr-defined]
            return event


@pytest.mark.asyncio
async def test_logout_stops_only_generations_from_exact_session() -> None:
    engine = TwoGenerationEngine()
    app = create_app(Settings(database_url=_database_url()), engine)
    async with app.router.lifespan_context(app):
        database = app.state.database
        await _reset(database)
        principal_a, principal_b = await _same_user_principals(database)
        service = app.state.generation_service
        generation_a, stream_a = await service.create(
            principal=principal_a,
            client_request_id=uuid.uuid4(),
            content="来自会话 A",
            conversation_id=None,
        )
        generation_b, stream_b = await service.create(
            principal=principal_b,
            client_request_id=uuid.uuid4(),
            content="来自会话 B",
            conversation_id=None,
        )
        iterator_a = stream_a.__aiter__()
        iterator_b = stream_b.__aiter__()
        await anext(iterator_a)
        await anext(iterator_b)
        await asyncio.gather(anext(iterator_a), anext(iterator_b))
        await asyncio.wait_for(engine.both_waiting.wait(), timeout=1)

        await service.logout(principal_a)
        engine.release.set()
        terminal_a, terminal_b = await asyncio.gather(
            _next_terminal(iterator_a), _next_terminal(iterator_b)
        )
        assert terminal_a.event_type == "generation.stopped"  # type: ignore[attr-defined]
        assert terminal_a.data["stoppedBy"] == "logout"  # type: ignore[attr-defined]
        assert terminal_b.event_type == "generation.completed"  # type: ignore[attr-defined]

        async with database.sessions() as session:
            session_a = await session.get(UserSession, principal_a.session_id)
            session_b = await session.get(UserSession, principal_b.session_id)
            persisted_a = await session.get(Generation, generation_a.generation_id)
            persisted_b = await session.get(Generation, generation_b.generation_id)
            assert session_a is not None and session_a.revoked_at is not None
            assert session_b is not None and session_b.revoked_at is None
            assert persisted_a is not None and persisted_a.status == "stopped"
            assert persisted_a.initiating_session_id == principal_a.session_id
            assert persisted_b is not None and persisted_b.status == "completed"
            assert persisted_b.initiating_session_id == principal_b.session_id


@pytest.mark.asyncio
async def test_retry_sequence_context_and_pages_ignore_equal_timestamps() -> None:
    app = create_app(Settings(database_url=_database_url()))
    async with app.router.lifespan_context(app):
        database = app.state.database
        await _reset(database)
        principal, _ = await _same_user_principals(database)
        repository = app.state.repository

        first = await repository.create_generation(
            principal=principal,
            client_request_id=uuid.uuid4(),
            content="第一问",
            conversation_id=None,
        )
        await repository.append_delta(first.generation_id, "失败片段")
        await repository.finish(first.generation_id, "failed", error_code="LLM_UNAVAILABLE")
        retry = await repository.create_retry(
            principal=principal,
            client_request_id=uuid.uuid4(),
            assistant_message_id=first.assistant_message_id,
        )
        await repository.append_delta(retry.generation_id, "重试成功")
        await repository.finish(retry.generation_id, "completed")
        second = await repository.create_generation(
            principal=principal,
            client_request_id=uuid.uuid4(),
            content="第二问",
            conversation_id=first.conversation_id,
        )
        assert second.prompt == [
            {"role": "user", "content": "第一问"},
            {"role": "assistant", "content": "重试成功"},
            {"role": "user", "content": "第二问"},
        ]
        await repository.finish(second.generation_id, "completed")

        equal_time = datetime(2026, 7, 17, tzinfo=UTC)
        async with database.sessions() as session, session.begin():
            await session.execute(update(Message).values(created_at=equal_time))
            sequences = list(
                await session.scalars(select(Message.sequence).order_by(Message.sequence))
            )
            assert sequences == [1, 2, 3, 4, 5]

        user_pages = [
            await repository.list_user_messages(
                user_id=principal.user_id,
                conversation_id=first.conversation_id,
                page=page,
                page_size=2,
            )
            for page in (1, 2, 3)
        ]
        admin_pages = [
            await repository.list_admin_messages(
                conversation_id=first.conversation_id,
                page=page,
                page_size=2,
            )
            for page in (1, 2, 3)
        ]
        assert [item["sequence"] for page in user_pages for item in page] == [1, 2, 3, 4, 5]
        assert user_pages == admin_pages


def test_token_budget_keeps_more_than_ten_turns_and_drops_earliest_whole_turns() -> None:
    turns = [(f"u-{index}", f"a-{index}") for index in range(12)]
    generous = TokenBudget(10_000, 500, 100)
    prompt, _ = select_complete_turns(turns, "current", generous)
    assert len(prompt) == 25
    assert prompt[0]["content"] == "u-0"

    exact_latest_two = TokenBudget(100, 20, 10)
    trimmed, estimate = select_complete_turns(turns, "current", exact_latest_two)
    assert estimate <= exact_latest_two.available_input_tokens
    assert len(trimmed) % 2 == 1
    assert trimmed[-1] == {"role": "user", "content": "current"}
    kept_history = trimmed[:-1]
    assert all(
        kept_history[index]["role"] == "user" and kept_history[index + 1]["role"] == "assistant"
        for index in range(0, len(kept_history), 2)
    )
    assert kept_history[0]["content"] != "u-0"


@pytest.mark.asyncio
async def test_current_input_over_budget_rolls_back_every_business_row() -> None:
    app = create_app(
        Settings(
            database_url=_database_url(),
            model_context_window_tokens=30,
            model_max_output_tokens=20,
            prompt_overhead_tokens=9,
        )
    )
    async with app.router.lifespan_context(app):
        database = app.state.database
        await _reset(database)
        principal, _ = await _same_user_principals(database)
        with pytest.raises(InputBudgetExceededError):
            await app.state.repository.create_generation(
                principal=principal,
                client_request_id=uuid.uuid4(),
                content="当前输入超过模型预算",
                conversation_id=None,
            )
        async with database.sessions() as session:
            for model in (Conversation, Message, Generation, LlmCall):
                assert await session.scalar(select(func.count()).select_from(model)) == 0
