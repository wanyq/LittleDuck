import asyncio
import hashlib
import json
import os
import uuid
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
import yaml
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from littleduck_api.config import Settings
from littleduck_api.context import conservative_token_estimate
from littleduck_api.main import create_app
from littleduck_api.models import User, UserSession


class FailingEngine:
    async def stream(self, _: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "部分"
        raise RuntimeError("deterministic provider failure")

    def count_tokens(self, prompt: list[dict[str, str]]) -> int:
        return conservative_token_estimate(prompt)


class StoppableEngine:
    def __init__(self) -> None:
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    async def stream(self, _: list[dict[str, str]]) -> AsyncIterator[str]:
        yield "部分"
        self.waiting.set()
        await self.release.wait()
        yield "不会持久化"

    def count_tokens(self, prompt: list[dict[str, str]]) -> int:
        return conservative_token_estimate(prompt)


def _contract() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[4] / "contracts" / "openapi.yaml"
    value = yaml.safe_load(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _resolve(contract: dict[str, Any], schema: dict[str, Any]) -> dict[str, Any]:
    reference = schema.get("$ref")
    if reference is None:
        return schema
    assert reference.startswith("#/components/schemas/")
    return contract["components"]["schemas"][reference.rsplit("/", 1)[-1]]


def _assert_schema(value: object, schema: dict[str, Any], contract: dict[str, Any]) -> None:
    schema = _resolve(contract, schema)
    if value is None:
        assert schema.get("nullable") is True
        return
    for part in schema.get("allOf", []):
        _assert_schema(value, part, contract)
    expected_type = schema.get("type")
    if expected_type == "object":
        assert isinstance(value, dict)
        required = set(schema.get("required", []))
        assert required <= set(value)
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            assert set(value) <= set(properties)
        for key, item in value.items():
            if key in properties:
                _assert_schema(item, properties[key], contract)
    elif expected_type == "array":
        assert isinstance(value, list)
        for item in value:
            _assert_schema(item, schema["items"], contract)
    elif expected_type == "string":
        assert isinstance(value, str)
        assert len(value) >= schema.get("minLength", 0)
        if "enum" in schema:
            assert value in schema["enum"]
        if schema.get("format") == "uuid":
            uuid.UUID(value)
        if schema.get("format") == "date-time":
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
            assert parsed.utcoffset() == timedelta(0)
    elif expected_type == "integer":
        assert isinstance(value, int) and not isinstance(value, bool)
        assert value >= schema.get("minimum", value)
    elif expected_type == "boolean":
        assert isinstance(value, bool)
    if "enum" in schema:
        assert value in schema["enum"]


def _events(source: str) -> list[tuple[str, dict[str, object]]]:
    result: list[tuple[str, dict[str, object]]] = []
    for frame in source.strip().split("\n\n"):
        lines = frame.splitlines()
        event_type = next(
            line.removeprefix("event: ") for line in lines if line.startswith("event: ")
        )
        data = json.loads(
            next(line.removeprefix("data: ") for line in lines if line.startswith("data: "))
        )
        assert isinstance(data, dict)
        result.append((event_type, data))
    return result


def _database_url() -> str:
    return os.environ.get(
        "TEST_DATABASE_URL",
        "postgresql+psycopg://littleduck_test:local-only@127.0.0.1:5432/littleduck_test",
    )


def test_implemented_vertical_slice_is_declared_by_baseline_contract() -> None:
    contract = _contract()
    application = create_app(Settings())
    implemented = application.openapi()["paths"]
    baseline = contract["paths"]
    for path, operations in implemented.items():
        assert path in baseline
        for method in operations:
            if method in {"get", "post", "put", "patch", "delete"}:
                assert method in baseline[path]


@pytest.mark.asyncio
async def test_actual_json_and_sse_payloads_match_closed_openapi_schemas() -> None:
    contract = _contract()
    schemas = contract["components"]["schemas"]
    app = create_app(Settings(database_url=_database_url()))
    raw_token = "strict-contract-session"
    async with app.router.lifespan_context(app):
        database = app.state.database
        async with database.sessions() as session, session.begin():
            await session.execute(
                text(
                    "TRUNCATE llm_calls, generations, messages, conversations, admin_sessions, "
                    "admins, user_sessions, users RESTART IDENTITY CASCADE"
                )
            )
            user = User(id=uuid.uuid4(), phone="13200132000")
            session.add(user)
            session.add(
                UserSession(
                    id=uuid.uuid4(),
                    user_id=user.id,
                    token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
                    expires_at=datetime.now(UTC) + timedelta(days=7),
                )
            )
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            health = await client.get("/healthz")
            _assert_schema(health.json(), schemas["HealthResponse"], contract)
            client.cookies.set("ld_user_session", raw_token)
            streamed = await client.post(
                "/api/v1/user/generations",
                json={"clientMessageId": str(uuid.uuid4()), "content": "严格合同"},
            )
            event_schemas = {
                "generation.started": "GenerationStartedEvent",
                "generation.delta": "GenerationDeltaEvent",
                "generation.completed": "GenerationCompletedEvent",
                "generation.failed": "GenerationFailedEvent",
                "generation.stopped": "GenerationStoppedEvent",
                "heartbeat": "HeartbeatEvent",
            }
            events = _events(streamed.text)
            for event_type, data in events:
                _assert_schema(data, schemas[event_schemas[event_type]], contract)
            generation_id = events[0][1]["generationId"]
            terminal = await client.get(f"/api/v1/user/generations/{generation_id}")
            _assert_schema(terminal.json(), schemas["GenerationResponse"], contract)

            invalid = await client.post(
                "/api/v1/user/generations",
                json={"clientMessageId": str(uuid.uuid4()), "content": "   "},
            )
            assert invalid.status_code == 400
            _assert_schema(invalid.json(), schemas["ErrorEnvelope"], contract)

    failing_app = create_app(Settings(database_url=_database_url()), FailingEngine())
    async with failing_app.router.lifespan_context(failing_app):
        async with AsyncClient(
            transport=ASGITransport(app=failing_app), base_url="http://test"
        ) as client:
            client.cookies.set("ld_user_session", raw_token)
            failed_stream = await client.post(
                "/api/v1/user/generations",
                json={"clientMessageId": str(uuid.uuid4()), "content": "严格失败合同"},
            )
        failed_events = _events(failed_stream.text)
        assert failed_events[-1][0] == "generation.failed"
        for event_type, data in failed_events:
            _assert_schema(data, schemas[event_schemas[event_type]], contract)
        assert failed_events[-1][1]["generation"]["errorCode"] == "LLM_UNAVAILABLE"

    stoppable_engine = StoppableEngine()
    stopped_app = create_app(Settings(database_url=_database_url()), stoppable_engine)
    async with stopped_app.router.lifespan_context(stopped_app):
        repository = stopped_app.state.repository
        principal = await repository.authenticate_user(raw_token)
        assert principal is not None
        service = stopped_app.state.generation_service
        created, event_stream = await service.create(
            principal=principal,
            client_request_id=uuid.uuid4(),
            content="严格停止合同",
            conversation_id=None,
        )
        iterator = event_stream.__aiter__()
        started = await anext(iterator)
        delta = await anext(iterator)
        await asyncio.wait_for(stoppable_engine.waiting.wait(), timeout=1)
        await service.request_stop(created.generation_id, principal)
        stoppable_engine.release.set()
        stopped = await asyncio.wait_for(anext(iterator), timeout=1)
        for event in (started, delta, stopped):
            _assert_schema(
                event.data,
                schemas[event_schemas[event.event_type]],
                contract,
            )
        assert stopped.event_type == "generation.stopped"
        assert stopped.data["generation"]["status"] == "stopped"
