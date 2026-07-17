import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from .models import Conversation, Generation, LlmCall, Message, User, UserSession


class ResourceNotFoundError(Exception):
    pass


class GenerationConflictError(Exception):
    pass


class DuplicateRequestError(Exception):
    def __init__(self, generation_id: uuid.UUID) -> None:
        super().__init__("duplicate client request")
        self.generation_id = generation_id


@dataclass(frozen=True)
class CreatedGeneration:
    generation_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    client_request_id: uuid.UUID
    kind: str
    title: str
    prompt: list[dict[str, str]]


class GenerationRepository:
    def __init__(self, sessions: async_sessionmaker[AsyncSession]) -> None:
        self._sessions = sessions

    async def authenticate_user(self, raw_token: str) -> uuid.UUID | None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        async with self._sessions() as session:
            statement = select(UserSession.user_id).where(
                UserSession.token_hash == token_hash,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > now,
            )
            user_id: uuid.UUID | None = await session.scalar(statement)
            return user_id

    async def create_generation(
        self,
        *,
        user_id: uuid.UUID,
        client_request_id: uuid.UUID,
        content: str,
        conversation_id: uuid.UUID | None,
        kind: str = "chat",
        retry_of_message_id: uuid.UUID | None = None,
    ) -> CreatedGeneration:
        normalized_content = content.strip()
        async with self._sessions() as session, session.begin():
            locked_user = await session.scalar(
                select(User.id).where(User.id == user_id).with_for_update()
            )
            if locked_user is None:
                raise ResourceNotFoundError

            duplicate = await session.scalar(
                select(Generation.id).where(
                    Generation.user_id == user_id,
                    Generation.client_request_id == client_request_id,
                )
            )
            if duplicate is not None:
                raise DuplicateRequestError(duplicate)

            context: list[dict[str, str]] = []
            if conversation_id is None:
                conversation = Conversation(
                    user_id=user_id,
                    title=normalized_content[:20],
                    title_status="temporary",
                )
                session.add(conversation)
                await session.flush()
            else:
                existing_conversation = await session.scalar(
                    select(Conversation).where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == user_id,
                    )
                )
                if existing_conversation is None:
                    raise ResourceNotFoundError
                conversation = existing_conversation

                active = await session.scalar(
                    select(Generation.id).where(
                        Generation.conversation_id == conversation.id,
                        Generation.status == "streaming",
                    )
                )
                if active is not None:
                    raise GenerationConflictError

                user_turn = aliased(Message)
                assistant_turn = aliased(Message)
                rows = (
                    await session.execute(
                        select(user_turn.content, assistant_turn.content)
                        .select_from(assistant_turn)
                        .join(user_turn, assistant_turn.reply_to_message_id == user_turn.id)
                        .where(
                            assistant_turn.conversation_id == conversation.id,
                            assistant_turn.role == "assistant",
                            assistant_turn.status == "completed",
                            user_turn.role == "user",
                            user_turn.status == "persisted",
                        )
                        .order_by(assistant_turn.created_at.desc())
                        .limit(10)
                    )
                ).all()
                for user_content, assistant_content in reversed(rows):
                    context.extend(
                        (
                            {"role": "user", "content": user_content},
                            {"role": "assistant", "content": assistant_content},
                        )
                    )

            user_message = Message(
                conversation_id=conversation.id,
                role="user",
                status="persisted",
                content=normalized_content,
            )
            session.add(user_message)
            await session.flush()

            assistant_message = Message(
                conversation_id=conversation.id,
                role="assistant",
                status="generating",
                content="",
                reply_to_message_id=user_message.id,
                retry_of_message_id=retry_of_message_id,
            )
            session.add(assistant_message)
            await session.flush()

            generation = Generation(
                user_id=user_id,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                client_request_id=client_request_id,
                kind=kind,
                status="streaming",
            )
            session.add(generation)
            await session.flush()

            prompt = [*context, {"role": "user", "content": normalized_content}]
            llm_call = LlmCall(
                conversation_id=conversation.id,
                generation_id=generation.id,
                related_message_id=assistant_message.id,
                call_type=kind,
                provider="openai",
                model="demo-model",
                prompt=prompt,
                response_text="",
                status="in_progress",
            )
            session.add(llm_call)

            return CreatedGeneration(
                generation_id=generation.id,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                client_request_id=client_request_id,
                kind=kind,
                title=conversation.title,
                prompt=prompt,
            )

    async def append_delta(self, generation_id: uuid.UUID, delta: str) -> str:
        async with self._sessions() as session, session.begin():
            generation = await session.get(Generation, generation_id, with_for_update=True)
            if generation is None:
                raise ResourceNotFoundError
            message = await session.get(Message, generation.assistant_message_id)
            call = await session.scalar(
                select(LlmCall).where(LlmCall.generation_id == generation_id)
            )
            if message is None or call is None:
                raise RuntimeError("generation persistence invariant violated")
            message.content += delta
            call.response_text += delta
            return message.content

    async def stop_requested(self, generation_id: uuid.UUID) -> bool:
        async with self._sessions() as session:
            value = await session.scalar(
                select(Generation.stop_requested).where(Generation.id == generation_id)
            )
            return bool(value)

    async def finish(
        self,
        generation_id: uuid.UUID,
        status: str,
        *,
        error_code: str | None = None,
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        message_status = {
            "completed": "completed",
            "failed": "failed",
            "stopped": "stopped",
        }[status]
        call_status = {
            "completed": "succeeded",
            "failed": "failed",
            "stopped": "stopped",
        }[status]
        async with self._sessions() as session, session.begin():
            generation = await session.get(Generation, generation_id, with_for_update=True)
            if generation is None:
                raise ResourceNotFoundError
            if generation.status != "streaming":
                return await self._view(session, generation)

            message = await session.get(Message, generation.assistant_message_id)
            call = await session.scalar(
                select(LlmCall).where(LlmCall.generation_id == generation_id)
            )
            conversation = await session.get(Conversation, generation.conversation_id)
            if message is None or call is None or conversation is None:
                raise RuntimeError("generation persistence invariant violated")

            generation.status = status
            generation.error_code = error_code
            generation.finished_at = now
            message.status = message_status
            call.status = call_status
            call.finished_at = now
            if error_code is not None:
                call.provider_error = {"code": error_code, "message": "generation failed"}
            conversation.last_activity_at = now
            await session.flush()
            await session.refresh(generation)
            await session.refresh(message)
            return await self._view(session, generation)

    async def request_stop(
        self, generation_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, object]:
        async with self._sessions() as session, session.begin():
            generation = await session.scalar(
                select(Generation)
                .where(Generation.id == generation_id, Generation.user_id == user_id)
                .with_for_update()
            )
            if generation is None:
                raise ResourceNotFoundError
            if generation.status == "streaming":
                generation.stop_requested = True
                await session.flush()
                await session.refresh(generation)
            return await self._view(session, generation)

    async def get_generation(
        self, generation_id: uuid.UUID, user_id: uuid.UUID
    ) -> dict[str, object]:
        async with self._sessions() as session:
            generation = await session.scalar(
                select(Generation).where(
                    Generation.id == generation_id,
                    Generation.user_id == user_id,
                )
            )
            if generation is None:
                raise ResourceNotFoundError
            return await self._view(session, generation)

    async def fail_interrupted_generations(self) -> int:
        async with self._sessions() as session:
            ids = list(
                await session.scalars(
                    select(Generation.id).where(Generation.status == "streaming")
                )
            )
        for generation_id in ids:
            await self.finish(generation_id, "failed", error_code="GENERATION_INTERRUPTED")
        return len(ids)

    async def _view(
        self, session: AsyncSession, generation: Generation
    ) -> dict[str, object]:
        message = await session.get(Message, generation.assistant_message_id)
        if message is None:
            raise RuntimeError("assistant message is missing")
        return {
            "generation": {
                "id": str(generation.id),
                "conversationId": str(generation.conversation_id),
                "userMessageId": str(generation.user_message_id),
                "assistantMessageId": str(generation.assistant_message_id),
                "kind": generation.kind,
                "status": generation.status,
                "stopRequested": generation.stop_requested,
                "errorCode": generation.error_code,
                "createdAt": generation.created_at.isoformat(),
                "updatedAt": generation.updated_at.isoformat(),
                "finishedAt": (
                    generation.finished_at.isoformat() if generation.finished_at else None
                ),
            },
            "assistantMessage": {
                "id": str(message.id),
                "conversationId": str(message.conversation_id),
                "role": message.role,
                "status": message.status,
                "content": message.content,
                "createdAt": message.created_at.isoformat(),
                "updatedAt": message.updated_at.isoformat(),
            },
        }
