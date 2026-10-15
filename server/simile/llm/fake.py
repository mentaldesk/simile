import asyncio
import inspect
import re
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable
from typing import TYPE_CHECKING

from simile.llm.provider import Request, Usage

if TYPE_CHECKING:
    from pydantic import BaseModel

type Reply = str | BaseModel | BaseException | Callable[[Request], str | Awaitable[str]]


class FakeProvider:
    """Scripted replies for tests, streamed a word at a time.

    Each call takes the next reply: a string, a pydantic model (sent as its JSON), an exception to
    raise, or a function of the request that returns a string, sync or async. When the script
    runs out, `default` is used, and without one the call fails.
    """

    name = "fake"

    def __init__(self, replies: Iterable[Reply] = (), *, default: str | None = None) -> None:
        self.replies: deque[Reply] = deque(replies)
        self.default = default
        self.requests: list[Request] = []

    async def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        self.requests.append(request)
        text = await self._next_reply(request)
        for chunk in re.findall(r"\s*\S+\s*", text) or [text]:
            await asyncio.sleep(0)
            yield chunk
        yield Usage(
            input_tokens=sum(len(m.content.split()) for m in request.messages),
            output_tokens=len(text.split()),
            model=f"fake-{request.model}",
        )

    async def _next_reply(self, request: Request) -> str:
        if self.replies:
            reply = self.replies.popleft()
        elif self.default is not None:
            reply = self.default
        else:
            raise AssertionError(f"FakeProvider has no reply left for {request.messages[-1]}")
        if isinstance(reply, BaseException):
            raise reply
        if callable(reply):
            reply = reply(request)
            if inspect.isawaitable(reply):
                reply = await reply
        return reply if isinstance(reply, str) else reply.model_dump_json()
