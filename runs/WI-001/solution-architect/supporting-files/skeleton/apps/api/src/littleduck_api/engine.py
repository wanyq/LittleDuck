import asyncio
from collections.abc import AsyncIterator
from typing import Protocol


class GenerationEngine(Protocol):
    def stream(self, prompt: list[dict[str, str]]) -> AsyncIterator[str]: ...


class DemoGenerationEngine:
    """Deterministic no-credential engine used only by the architecture slice."""

    async def stream(self, prompt: list[dict[str, str]]) -> AsyncIterator[str]:
        latest = prompt[-1]["content"]
        for chunk in ("收到：", latest, "。这是本地演示回复。"):
            await asyncio.sleep(0)
            yield chunk
