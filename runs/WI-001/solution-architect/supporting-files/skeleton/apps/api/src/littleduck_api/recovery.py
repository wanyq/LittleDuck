import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress


class InterruptedGenerationRecovery:
    def __init__(self, reconcile: Callable[[], Awaitable[int]]) -> None:
        self._reconcile = reconcile
        self._lock = asyncio.Lock()
        self.complete = False

    async def reconcile_once(self) -> bool:
        if self.complete:
            return True
        async with self._lock:
            if self.complete:
                return True
            try:
                await self._reconcile()
            except Exception:
                return False
            self.complete = True
            return True

    async def retry_until_complete(
        self,
        database_ready: Callable[[], Awaitable[bool]],
        interval_seconds: float,
    ) -> None:
        while not self.complete:
            if await database_ready():
                await self.reconcile_once()
            if not self.complete:
                await asyncio.sleep(interval_seconds)


async def stop_recovery_task(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
