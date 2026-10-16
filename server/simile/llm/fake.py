import asyncio
import inspect
import re
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from typing import TYPE_CHECKING

from simile.llm.provider import Request, Usage

if TYPE_CHECKING:
    from pydantic import BaseModel

type Step = str | asyncio.Event | BaseException
type Reply = (
    str | BaseModel | BaseException | list[Step] | Callable[[Request], str | Awaitable[str]]
)


class FakeProvider:
    """Scripted replies for tests. The README lists what a reply can be."""

    name = "fake"

    def __init__(self, replies: Iterable[Reply] = (), *, default: str | None = None) -> None:
        self.replies: deque[Reply] = deque(replies)
        self.default = default
        self.requests: list[Request] = []
        self.warmed: list[tuple[str, str]] = []

    async def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        self.requests.append(request)
        text = ""
        for step in await self._next_steps(request):
            if isinstance(step, BaseException):
                raise step
            if isinstance(step, asyncio.Event):
                await step.wait()
                continue
            await asyncio.sleep(0)
            text += step
            yield step
        yield Usage(
            input_tokens=sum(len(m.content.split()) for m in request.messages),
            output_tokens=len(text.split()),
            model=f"fake-{request.model}",
        )

    def warm(self, system: str, model: str) -> None:
        self.warmed.append((system, model))

    async def _next_steps(self, request: Request) -> list[Step]:
        if self.replies:
            reply = self.replies.popleft()
        elif self.default is not None:
            reply = self.default
        else:
            raise AssertionError(f"FakeProvider has no reply left for {request.messages[-1]}")
        if callable(reply):
            reply = reply(request)
            if inspect.isawaitable(reply):
                reply = await reply
        if isinstance(reply, str):
            return re.findall(r"\s*\S+\s*", reply) or [reply]
        if isinstance(reply, list):
            return reply
        if isinstance(reply, BaseException):
            return [reply]
        return [reply.model_dump_json()]
