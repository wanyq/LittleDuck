import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import aliased

from .context import TokenBudget, TokenCounter, select_complete_turns
from .models import Conversation, Generation, LlmCall, Message, UserSession
from .time import utc_iso


class ResourceNotFoundError(Exception):
    pass


class GenerationConflictError(Exception):
    pass


class RetryNotAllowedError(Exception):
    pass


class InvalidContentError(Exception):
    pass


class InputBudgetExceededError(Exception):
    pass


class DuplicateRequestError(Exception):
    def __init__(self, generation_id: uuid.UUID) -> None:
        super().__init__("duplicate client request")
        self.generation_id = generation_id


@dataclass(frozen=True)
class UserPrincipal:
    user_id: uuid.UUID
    session_id: uuid.UUID


@dataclass(frozen=True)
class CreatedGeneration:
    generation_id: uuid.UUID
    conversation_id: uuid.UUID
    user_message_id: uuid.UUID
    assistant_message_id: uuid.UUID
    initiating_session_id: uuid.UUID
    client_request_id: uuid.UUID
    kind: str
    title: str
    prompt: list[dict[str, str]]


class GenerationRepository:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        *,
        token_budget: TokenBudget,
        count_tokens: TokenCounter,
    ) -> None:
        self._sessions = sessions
        self._token_budget = token_budget
        self._count_tokens = count_tokens

    async def authenticate_user(self, raw_token: str) -> UserPrincipal | None:
        token_hash = hashlib.sha256(raw_token.encode("utf-8")).hexdigest()
        now = datetime.now(UTC)
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(UserSession.user_id, UserSession.id).where(
                        UserSession.token_hash == token_hash,
                        UserSession.revoked_at.is_(None),
                        UserSession.expires_at > now,
                    )
                )
            ).one_or_none()
            if row is None:
                return None
            return UserPrincipal(user_id=row.user_id, session_id=row.id)

    async def create_generation(
        self,
        *,
        principal: UserPrincipal,
        client_request_id: uuid.UUID,
        content: str,
        conversation_id: uuid.UUID | None,
    ) -> CreatedGeneration:
        normalized_content = self._normalize_content(content)
        async with self._sessions() as session, session.begin():
            await self._lock_principal(session, principal)
            await self._reject_duplicate(session, principal.user_id, client_request_id)

            if conversation_id is None:
                conversation = Conversation(
                    user_id=principal.user_id,
                    title=normalized_content[:20],
                    title_status="temporary",
                    next_message_sequence=1,
                )
                session.add(conversation)
                await session.flush()
            else:
                locked_conversation = await session.scalar(
                    select(Conversation)
                    .where(
                        Conversation.id == conversation_id,
                        Conversation.user_id == principal.user_id,
                    )
                    .with_for_update()
                )
                if locked_conversation is None:
                    raise ResourceNotFoundError
                conversation = locked_conversation
                await self._reject_active_generation(session, conversation.id)

            prompt, estimate = await self._prompt_for_new_message(
                session, conversation.id, normalized_content
            )
            user_sequence = self._reserve_sequences(conversation, 2)
            user_message = Message(
                conversation_id=conversation.id,
                sequence=user_sequence,
                role="user",
                status="persisted",
                content=normalized_content,
            )
            session.add(user_message)
            await session.flush()

            assistant_message = Message(
                conversation_id=conversation.id,
                sequence=user_sequence + 1,
                role="assistant",
                status="generating",
                content="",
                reply_to_message_id=user_message.id,
            )
            session.add(assistant_message)
            await session.flush()

            generation = self._new_generation(
                principal=principal,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                client_request_id=client_request_id,
                kind="chat",
            )
            session.add(generation)
            await session.flush()
            session.add(
                self._new_llm_call(
                    generation,
                    assistant_message.id,
                    prompt,
                    estimate,
                    call_type="chat",
                )
            )

            return CreatedGeneration(
                generation_id=generation.id,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=assistant_message.id,
                initiating_session_id=principal.session_id,
                client_request_id=client_request_id,
                kind="chat",
                title=conversation.title,
                prompt=prompt,
            )

    async def create_retry(
        self,
        *,
        principal: UserPrincipal,
        client_request_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
    ) -> CreatedGeneration:
        async with self._sessions() as session, session.begin():
            await self._lock_principal(session, principal)
            await self._reject_duplicate(session, principal.user_id, client_request_id)
            source = await session.scalar(
                select(Message)
                .join(Conversation, Conversation.id == Message.conversation_id)
                .where(
                    Message.id == assistant_message_id,
                    Message.role == "assistant",
                    Message.status.in_(("failed", "stopped")),
                    Conversation.user_id == principal.user_id,
                )
            )
            if source is None or source.reply_to_message_id is None:
                raise RetryNotAllowedError
            later_assistant = await session.scalar(
                select(Message.id).where(
                    Message.conversation_id == source.conversation_id,
                    Message.role == "assistant",
                    Message.sequence > source.sequence,
                )
            )
            if later_assistant is not None:
                raise RetryNotAllowedError

            conversation = await session.scalar(
                select(Conversation)
                .where(Conversation.id == source.conversation_id)
                .with_for_update()
            )
            user_message = await session.get(Message, source.reply_to_message_id)
            if conversation is None or user_message is None:
                raise RuntimeError("retry persistence invariant violated")
            await self._reject_active_generation(session, conversation.id)
            prompt, estimate = await self._prompt_for_new_message(
                session,
                conversation.id,
                user_message.content,
                before_sequence=user_message.sequence,
            )
            assistant_sequence = self._reserve_sequences(conversation, 1)
            retry_message = Message(
                conversation_id=conversation.id,
                sequence=assistant_sequence,
                role="assistant",
                status="generating",
                content="",
                reply_to_message_id=user_message.id,
                retry_of_message_id=source.id,
            )
            session.add(retry_message)
            await session.flush()
            generation = self._new_generation(
                principal=principal,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=retry_message.id,
                client_request_id=client_request_id,
                kind="retry",
            )
            session.add(generation)
            await session.flush()
            session.add(
                self._new_llm_call(
                    generation,
                    retry_message.id,
                    prompt,
                    estimate,
                    call_type="retry",
                )
            )
            return CreatedGeneration(
                generation_id=generation.id,
                conversation_id=conversation.id,
                user_message_id=user_message.id,
                assistant_message_id=retry_message.id,
                initiating_session_id=principal.session_id,
                client_request_id=client_request_id,
                kind="retry",
                title=conversation.title,
                prompt=prompt,
            )

    async def append_delta(self, generation_id: uuid.UUID, delta: str) -> str:
        if delta == "":
            raise ValueError("empty generation delta is not persistable")
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

    async def stop_request(self, generation_id: uuid.UUID) -> tuple[bool, str | None]:
        async with self._sessions() as session:
            row = (
                await session.execute(
                    select(Generation.stop_requested, Generation.stop_requested_by).where(
                        Generation.id == generation_id
                    )
                )
            ).one_or_none()
            if row is None:
                return False, None
            return bool(row.stop_requested), row.stop_requested_by

    async def finish(
        self,
        generation_id: uuid.UUID,
        status: str,
        *,
        error_code: str | None = None,
    ) -> dict[str, object]:
        now = datetime.now(UTC)
        message_status = {"completed": "completed", "failed": "failed", "stopped": "stopped"}[
            status
        ]
        call_status = {"completed": "succeeded", "failed": "failed", "stopped": "stopped"}[
            status
        ]
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
                generation.stop_requested_by = "user"
                await session.flush()
                await session.refresh(generation)
            return await self._view(session, generation)

    async def logout_user(self, principal: UserPrincipal) -> list[uuid.UUID]:
        now = datetime.now(UTC)
        async with self._sessions() as session, session.begin():
            current_session = await session.scalar(
                select(UserSession)
                .where(
                    UserSession.id == principal.session_id,
                    UserSession.user_id == principal.user_id,
                )
                .with_for_update()
            )
            if current_session is None:
                return []
            if current_session.revoked_at is None:
                current_session.revoked_at = now
            generations = list(
                await session.scalars(
                    select(Generation)
                    .where(
                        Generation.initiating_session_id == principal.session_id,
                        Generation.status == "streaming",
                    )
                    .with_for_update()
                )
            )
            for generation in generations:
                generation.stop_requested = True
                generation.stop_requested_by = "logout"
            return [generation.id for generation in generations]

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

    async def list_user_messages(
        self,
        *,
        user_id: uuid.UUID,
        conversation_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> list[dict[str, object]]:
        async with self._sessions() as session:
            owned = await session.scalar(
                select(Conversation.id).where(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user_id,
                )
            )
            if owned is None:
                raise ResourceNotFoundError
            return await self._message_page(session, conversation_id, page, page_size)

    async def list_admin_messages(
        self,
        *,
        conversation_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> list[dict[str, object]]:
        async with self._sessions() as session:
            conversation = await session.get(Conversation, conversation_id)
            if conversation is None:
                raise ResourceNotFoundError
            return await self._message_page(session, conversation_id, page, page_size)

    async def fail_interrupted_generations(self, startup_cutoff: datetime) -> int:
        async with self._sessions() as session:
            ids = list(
                await session.scalars(
                    select(Generation.id).where(
                        Generation.status == "streaming",
                        Generation.created_at < startup_cutoff,
                    )
                )
            )
        for generation_id in ids:
            await self.finish(generation_id, "failed", error_code="GENERATION_INTERRUPTED")
        return len(ids)

    async def _prompt_for_new_message(
        self,
        session: AsyncSession,
        conversation_id: uuid.UUID,
        current_content: str,
        *,
        before_sequence: int | None = None,
    ) -> tuple[list[dict[str, str]], int]:
        user_turn = aliased(Message)
        assistant_turn = aliased(Message)
        statement = (
            select(user_turn.content, assistant_turn.content)
            .select_from(assistant_turn)
            .join(user_turn, assistant_turn.reply_to_message_id == user_turn.id)
            .where(
                assistant_turn.conversation_id == conversation_id,
                assistant_turn.role == "assistant",
                assistant_turn.status == "completed",
                user_turn.role == "user",
                user_turn.status == "persisted",
            )
            .order_by(assistant_turn.sequence.asc())
        )
        if before_sequence is not None:
            statement = statement.where(assistant_turn.sequence < before_sequence)
        rows = [(row[0], row[1]) for row in (await session.execute(statement)).all()]
        prompt, estimate = select_complete_turns(
            rows,
            current_content,
            self._token_budget,
            self._count_tokens,
        )
        if estimate > self._token_budget.available_input_tokens:
            raise InputBudgetExceededError
        return prompt, estimate

    async def _lock_principal(
        self, session: AsyncSession, principal: UserPrincipal
    ) -> UserSession:
        current = await session.scalar(
            select(UserSession)
            .where(
                UserSession.id == principal.session_id,
                UserSession.user_id == principal.user_id,
                UserSession.revoked_at.is_(None),
                UserSession.expires_at > datetime.now(UTC),
            )
            .with_for_update()
        )
        if current is None:
            raise PermissionError
        return current

    @staticmethod
    async def _reject_duplicate(
        session: AsyncSession, user_id: uuid.UUID, client_request_id: uuid.UUID
    ) -> None:
        duplicate = await session.scalar(
            select(Generation.id).where(
                Generation.user_id == user_id,
                Generation.client_request_id == client_request_id,
            )
        )
        if duplicate is not None:
            raise DuplicateRequestError(duplicate)

    @staticmethod
    async def _reject_active_generation(
        session: AsyncSession, conversation_id: uuid.UUID
    ) -> None:
        active = await session.scalar(
            select(Generation.id).where(
                Generation.conversation_id == conversation_id,
                Generation.status == "streaming",
            )
        )
        if active is not None:
            raise GenerationConflictError

    @staticmethod
    def _reserve_sequences(conversation: Conversation, count: int) -> int:
        first = conversation.next_message_sequence
        conversation.next_message_sequence += count
        return first

    @staticmethod
    def _normalize_content(content: str) -> str:
        normalized = content.strip()
        if not 1 <= len(normalized) <= 4000:
            raise InvalidContentError
        return normalized

    @staticmethod
    def _new_generation(
        *,
        principal: UserPrincipal,
        conversation_id: uuid.UUID,
        user_message_id: uuid.UUID,
        assistant_message_id: uuid.UUID,
        client_request_id: uuid.UUID,
        kind: str,
    ) -> Generation:
        return Generation(
            user_id=principal.user_id,
            initiating_session_id=principal.session_id,
            conversation_id=conversation_id,
            user_message_id=user_message_id,
            assistant_message_id=assistant_message_id,
            client_request_id=client_request_id,
            kind=kind,
            status="streaming",
        )

    def _new_llm_call(
        self,
        generation: Generation,
        related_message_id: uuid.UUID,
        prompt: list[dict[str, str]],
        input_tokens_estimated: int,
        *,
        call_type: str,
    ) -> LlmCall:
        return LlmCall(
            conversation_id=generation.conversation_id,
            generation_id=generation.id,
            related_message_id=related_message_id,
            call_type=call_type,
            provider="openai",
            model="demo-model",
            input_tokens_estimated=input_tokens_estimated,
            max_output_tokens=self._token_budget.max_output_tokens,
            prompt=prompt,
            response_text="",
            status="in_progress",
        )

    async def _message_page(
        self,
        session: AsyncSession,
        conversation_id: uuid.UUID,
        page: int,
        page_size: int,
    ) -> list[dict[str, object]]:
        messages = list(
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation_id)
                .order_by(Message.sequence.asc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        )
        return [self._message_view(message) for message in messages]

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
                "startedAt": utc_iso(generation.created_at),
                "createdAt": utc_iso(generation.created_at),
                "updatedAt": utc_iso(generation.updated_at),
                "finishedAt": utc_iso(generation.finished_at) if generation.finished_at else None,
            },
            "assistantMessage": self._message_view(message, generation_id=generation.id),
        }

    @staticmethod
    def _message_view(
        message: Message, *, generation_id: uuid.UUID | None = None
    ) -> dict[str, object]:
        view: dict[str, object] = {
            "id": str(message.id),
            "conversationId": str(message.conversation_id),
            "sequence": message.sequence,
            "role": message.role,
            "status": message.status,
            "content": message.content,
            "createdAt": utc_iso(message.created_at),
            "updatedAt": utc_iso(message.updated_at),
        }
        if message.reply_to_message_id is not None:
            view["replyToMessageId"] = str(message.reply_to_message_id)
        if message.retry_of_message_id is not None:
            view["retryOfMessageId"] = str(message.retry_of_message_id)
        if generation_id is not None:
            view["generationId"] = str(generation_id)
            view["canRetry"] = message.status in {"failed", "stopped"}
        return view
