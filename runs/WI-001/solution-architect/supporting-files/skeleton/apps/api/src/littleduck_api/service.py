import asyncio
import contextlib
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from .engine import GenerationEngine
from .repository import CreatedGeneration, GenerationRepository, UserPrincipal
from .time import utc_now_iso


@dataclass(frozen=True)
class DomainEvent:
    event_type: str
    data: dict[str, Any]
    terminal: bool = False


@dataclass
class RuntimeState:
    stop: asyncio.Event = field(default_factory=asyncio.Event)
    subscribers: set[asyncio.Queue[DomainEvent]] = field(default_factory=set)
    task: asyncio.Task[None] | None = None
    sequence: int = 1
    stop_reason: str = "user"


class GenerationService:
    def __init__(self, repository: GenerationRepository, engine: GenerationEngine) -> None:
        self._repository = repository
        self._engine = engine
        self._states: dict[uuid.UUID, RuntimeState] = {}

    async def create(
        self,
        *,
        principal: UserPrincipal,
        client_request_id: uuid.UUID,
        content: str,
        conversation_id: uuid.UUID | None,
    ) -> tuple[CreatedGeneration, AsyncIterator[DomainEvent]]:
        created = await self._repository.create_generation(
            principal=principal,
            client_request_id=client_request_id,
            content=content,
            conversation_id=conversation_id,
        )
        return self._start(created)

    async def retry(
        self,
        *,
        principal: UserPrincipal,
        client_request_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> tuple[CreatedGeneration, AsyncIterator[DomainEvent]]:
        created = await self._repository.create_retry(
            principal=principal,
            client_request_id=client_request_id,
            assistant_message_id=assistant_message_id,
        )
        return self._start(created)

    def _start(
        self, created: CreatedGeneration
    ) -> tuple[CreatedGeneration, AsyncIterator[DomainEvent]]:
        state = RuntimeState()
        queue: asyncio.Queue[DomainEvent] = asyncio.Queue()
        state.subscribers.add(queue)
        self._states[created.generation_id] = state
        state.task = asyncio.create_task(self._run(created, state))

        async def events() -> AsyncIterator[DomainEvent]:
            yield DomainEvent(
                "generation.started",
                {
                    "generationId": str(created.generation_id),
                    "conversationId": str(created.conversation_id),
                    "userMessageId": str(created.user_message_id),
                    "assistantMessageId": str(created.assistant_message_id),
                    "kind": created.kind,
                    "sequence": 1,
                    "temporaryTitle": created.title,
                    "occurredAt": utc_now_iso(),
                },
            )
            try:
                while True:
                    event = await queue.get()
                    yield event
                    if event.terminal:
                        break
            finally:
                state.subscribers.discard(queue)

        return created, events()

    async def request_stop(
        self, generation_id: uuid.UUID, principal: UserPrincipal
    ) -> dict[str, object]:
        view = await self._repository.request_stop(generation_id, principal.user_id)
        state = self._states.get(generation_id)
        if state is not None:
            state.stop_reason = "user"
            state.stop.set()
        return view

    async def logout(self, principal: UserPrincipal) -> None:
        for generation_id in await self._repository.logout_user(principal):
            state = self._states.get(generation_id)
            if state is not None:
                state.stop_reason = "logout"
                state.stop.set()

    async def shutdown(self) -> None:
        tasks: list[asyncio.Task[None]] = []
        for state in self._states.values():
            if state.task is not None:
                state.task.cancel()
                tasks.append(state.task)
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _run(self, created: CreatedGeneration, state: RuntimeState) -> None:
        try:
            async for delta in self._engine.stream(created.prompt):
                requested, reason = await self._repository.stop_request(created.generation_id)
                if state.stop.is_set() or requested:
                    await self._stop(created.generation_id, state, reason or state.stop_reason)
                    return
                if delta == "":
                    continue
                content = await self._repository.append_delta(created.generation_id, delta)
                state.sequence += 1
                self._publish(
                    state,
                    DomainEvent(
                        "generation.delta",
                        {
                            "generationId": str(created.generation_id),
                            "assistantMessageId": str(created.assistant_message_id),
                            "sequence": state.sequence,
                            "delta": delta,
                            "accumulatedLength": len(content),
                            "occurredAt": utc_now_iso(),
                        },
                    ),
                )

            requested, reason = await self._repository.stop_request(created.generation_id)
            if state.stop.is_set() or requested:
                await self._stop(created.generation_id, state, reason or state.stop_reason)
                return

            view = await self._repository.finish(created.generation_id, "completed")
            state.sequence += 1
            self._publish(
                state,
                DomainEvent(
                    "generation.completed",
                    {
                        "generationId": str(created.generation_id),
                        "sequence": state.sequence,
                        "titleWillBeAttempted": False,
                        "occurredAt": utc_now_iso(),
                        **view,
                    },
                    terminal=True,
                ),
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            view = await self._repository.finish(
                created.generation_id, "failed", error_code="LLM_UNAVAILABLE"
            )
            state.sequence += 1
            self._publish(
                state,
                DomainEvent(
                    "generation.failed",
                    {
                        "generationId": str(created.generation_id),
                        "sequence": state.sequence,
                        "error": {
                            "code": "LLM_UNAVAILABLE",
                            "message": "回复生成失败，请稍后重试",
                            "retryable": True,
                        },
                        "occurredAt": utc_now_iso(),
                        **view,
                    },
                    terminal=True,
                ),
            )
        finally:
            self._states.pop(created.generation_id, None)

    async def _stop(
        self, generation_id: uuid.UUID, state: RuntimeState, stopped_by: str
    ) -> None:
        view = await self._repository.finish(generation_id, "stopped")
        state.sequence += 1
        self._publish(
            state,
            DomainEvent(
                "generation.stopped",
                {
                    "generationId": str(generation_id),
                    "sequence": state.sequence,
                    "stoppedBy": stopped_by,
                    "occurredAt": utc_now_iso(),
                    **view,
                },
                terminal=True,
            ),
        )

    @staticmethod
    def _publish(state: RuntimeState, event: DomainEvent) -> None:
        for subscriber in tuple(state.subscribers):
            with contextlib.suppress(asyncio.QueueFull):
                subscriber.put_nowait(event)
