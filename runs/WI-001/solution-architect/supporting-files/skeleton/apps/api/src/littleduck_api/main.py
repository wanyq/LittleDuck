import asyncio
import json
import uuid
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any

from fastapi import Cookie, Depends, FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, StreamingResponse

from .config import Settings, get_settings
from .context import TokenBudget
from .db import Database
from .engine import DemoGenerationEngine, GenerationEngine
from .recovery import InterruptedGenerationRecovery, stop_recovery_task
from .repository import (
    DuplicateRequestError,
    GenerationConflictError,
    GenerationRepository,
    InputBudgetExceededError,
    InvalidContentError,
    ResourceNotFoundError,
    RetryNotAllowedError,
    UserPrincipal,
)
from .schemas import CreateGenerationRequest, RetryGenerationRequest
from .service import DomainEvent, GenerationService
from .time import utc_now_iso


def _error(code: str, message: str, status_code: int, **extra: object) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "requestId": "architecture-slice",
                **extra,
            }
        },
    )


def _encode_sse(event: DomainEvent) -> bytes:
    data = json.dumps(event.data, ensure_ascii=False, separators=(",", ":"))
    return f"event: {event.event_type}\ndata: {data}\n\n".encode()


def create_app(
    settings: Settings | None = None,
    engine: GenerationEngine | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    database = Database(resolved_settings.database_url)
    resolved_engine = engine or DemoGenerationEngine()
    repository = GenerationRepository(
        database.sessions,
        token_budget=TokenBudget(
            context_window_tokens=resolved_settings.model_context_window_tokens,
            max_output_tokens=resolved_settings.model_max_output_tokens,
            prompt_overhead_tokens=resolved_settings.prompt_overhead_tokens,
        ),
        count_tokens=resolved_engine.count_tokens,
    )
    service = GenerationService(repository, resolved_engine)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        startup_cutoff = datetime.now(UTC)
        recovery = InterruptedGenerationRecovery(
            lambda: repository.fail_interrupted_generations(startup_cutoff)
        )
        application.state.recovery = recovery
        recovery_task = asyncio.create_task(
            recovery.retry_until_complete(
                database.ready,
                resolved_settings.recovery_retry_seconds,
            )
        )
        try:
            yield
        finally:
            await stop_recovery_task(recovery_task)
            await service.shutdown()
            await database.dispose()

    application = FastAPI(
        title="LittleDuck MVP API architecture slice",
        version="0.2.0",
        lifespan=lifespan,
    )
    application.state.settings = resolved_settings
    application.state.database = database
    application.state.repository = repository
    application.state.generation_service = service

    @application.middleware("http")
    async def same_origin_write_guard(
        request: Request,
        call_next: Callable[[Request], Awaitable[Any]],
    ) -> Any:
        if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
            origin = request.headers.get("origin")
            allowed_origin = (
                resolved_settings.admin_origin
                if request.url.path.startswith("/api/v1/admin")
                else resolved_settings.public_origin
            )
            if origin is not None and origin != allowed_origin:
                return _error("FORBIDDEN", "请求来源不受信任", 403)
            fetch_site = request.headers.get("sec-fetch-site")
            if fetch_site not in {None, "same-origin", "none"}:
                return _error("FORBIDDEN", "请求来源不受信任", 403)
            if request.headers.get("content-length") not in {None, "0"}:
                content_type = request.headers.get("content-type", "")
                if not content_type.startswith("application/json"):
                    return _error("UNSUPPORTED_MEDIA_TYPE", "请求必须使用 JSON", 415)
        return await call_next(request)

    async def current_user(
        ld_user_session: str | None = Cookie(default=None),
    ) -> UserPrincipal:
        if ld_user_session is None:
            raise PermissionError
        principal = await repository.authenticate_user(ld_user_session)
        if principal is None:
            raise PermissionError
        return principal

    @application.exception_handler(PermissionError)
    async def permission_error_handler(_: Request, __: PermissionError) -> JSONResponse:
        return _error("UNAUTHENTICATED", "登录状态已失效，请重新登录", 401)

    @application.exception_handler(ResourceNotFoundError)
    async def not_found_handler(_: Request, __: ResourceNotFoundError) -> JSONResponse:
        return _error("RESOURCE_NOT_FOUND", "资源不存在", 404)

    @application.exception_handler(GenerationConflictError)
    async def conflict_handler(_: Request, __: GenerationConflictError) -> JSONResponse:
        return _error("GENERATION_IN_PROGRESS", "当前会话正在生成回复", 409)

    @application.exception_handler(RetryNotAllowedError)
    async def retry_error_handler(_: Request, __: RetryNotAllowedError) -> JSONResponse:
        return _error("RETRY_NOT_ALLOWED", "该回复当前不可重试", 409)

    @application.exception_handler(RequestValidationError)
    async def validation_error_handler(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        details = [
            {
                "field": ".".join(str(part) for part in error["loc"] if part != "body"),
                "issue": error["msg"],
            }
            for error in exc.errors()
        ]
        return _error("VALIDATION_ERROR", "请求参数不正确", 400, details=details)

    @application.exception_handler(InvalidContentError)
    @application.exception_handler(InputBudgetExceededError)
    async def content_error_handler(_: Request, __: Exception) -> JSONResponse:
        return _error(
            "VALIDATION_ERROR",
            "消息内容超出当前模型可接受范围",
            400,
            details=[{"field": "content", "issue": "trim 后须为 1 至 4000 字符并适合模型上下文"}],
        )

    @application.exception_handler(DuplicateRequestError)
    async def duplicate_handler(_: Request, exc: DuplicateRequestError) -> JSONResponse:
        return _error(
            "DUPLICATE_MESSAGE",
            "该消息已经提交，请读取已有生成状态",
            409,
            generationId=str(exc.generation_id),
        )

    @application.get("/healthz")
    async def health() -> JSONResponse:
        database_ready = await database.ready()
        recovery: InterruptedGenerationRecovery = application.state.recovery
        recovered = await recovery.reconcile_once() if database_ready else False
        ready = database_ready and recovered
        return JSONResponse(
            status_code=200 if ready else 503,
            content={
                "status": "ok" if ready else "degraded",
                "database": "ok" if database_ready else "unavailable",
                "time": utc_now_iso(),
            },
        )

    @application.post("/api/v1/user/generations")
    async def create_generation(
        payload: CreateGenerationRequest,
        principal: UserPrincipal = Depends(current_user),
    ) -> StreamingResponse:
        _, events = await service.create(
            principal=principal,
            client_request_id=payload.client_message_id,
            content=payload.content,
            conversation_id=payload.conversation_id,
        )

        async def stream() -> AsyncIterator[bytes]:
            async for event in events:
                yield _encode_sse(event)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache, no-transform",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/api/v1/user/generations/{generationId}")
    async def get_generation(
        generationId: uuid.UUID,
        principal: UserPrincipal = Depends(current_user),
    ) -> dict[str, object]:
        return await repository.get_generation(generationId, principal.user_id)

    @application.post("/api/v1/user/generations/{generationId}/stop")
    async def stop_generation(
        generationId: uuid.UUID,
        principal: UserPrincipal = Depends(current_user),
    ) -> JSONResponse:
        view = await service.request_stop(generationId, principal)
        generation = view["generation"]
        assert isinstance(generation, dict)
        status_code = 202 if generation["status"] == "streaming" else 200
        return JSONResponse(status_code=status_code, content=view)

    @application.post("/api/v1/user/assistant-messages/{assistantMessageId}/retries")
    async def retry_generation(
        assistantMessageId: uuid.UUID,
        payload: RetryGenerationRequest,
        principal: UserPrincipal = Depends(current_user),
    ) -> StreamingResponse:
        _, events = await service.retry(
            principal=principal,
            client_request_id=payload.client_retry_id,
            assistant_message_id=assistantMessageId,
        )

        async def stream() -> AsyncIterator[bytes]:
            async for event in events:
                yield _encode_sse(event)

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

    @application.post("/api/v1/user/auth/logout", status_code=204)
    async def logout_user(
        principal: UserPrincipal = Depends(current_user),
    ) -> Response:
        await service.logout(principal)
        response = Response(status_code=204)
        response.delete_cookie(
            resolved_settings.user_session_cookie,
            path="/api/v1/user",
            httponly=True,
            samesite="lax",
        )
        return response

    return application


app = create_app()
