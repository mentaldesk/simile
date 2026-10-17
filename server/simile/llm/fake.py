import asyncio
import inspect
import re
from collections import deque
from collections.abc import AsyncGenerator, Awaitable, Callable, Iterable, Sequence
from itertools import cycle, islice
from typing import TYPE_CHECKING

from simile.llm.provider import Request, Usage

if TYPE_CHECKING:
    from pydantic import BaseModel

CAST = re.compile(r"^It's [^\n]*?\. (\w+) has just walked up to (\w+)\.$", re.MULTILINE)
PLANNED = re.compile(r"\bAbout (\d+) lines in all\b")
GOODBYES = ("Anyway, I'd better get on. Bye for now!", "Bye, take care!")

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


def cast(request: Request) -> tuple[str, str, int] | None:
    """Who a B2 scene request is between, the one who walks up first, and how many lines it's
    planned to run. None for any other request."""
    prompt = request.messages[-1].content
    found = CAST.search(prompt)
    if found is None:
        return None
    planned = PLANNED.search(prompt)
    return found[1], found[2], int(planned[1]) if planned else 2 * len(GOODBYES)


def scene(request: Request, lines: Sequence[str]) -> str | None:
    """A B2 scene request answered with its script: `lines` in turn, then a goodbye and its
    answer, as many lines in all as it's planned to run. None for any other request."""
    found = cast(request)
    if found is None:
        return None
    a, b, length = found
    said = [*islice(cycle(lines), max(length - len(GOODBYES), 0)), *GOODBYES]
    return "".join(
        f"{name}: {line} [values: connection]\n" for name, line in zip(cycle((a, b)), said)
    )
