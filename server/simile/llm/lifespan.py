import itertools
import os
from collections.abc import AsyncGenerator, AsyncIterator, Sequence
from contextlib import asynccontextmanager

from starlette.applications import Starlette

from simile.llm.client import LLMClient
from simile.llm.fake import FakeProvider
from simile.llm.provider import Request, Usage

FAKE_ENV = "SIMILE_LLM"

CANNED = (
    "Morning! How are things with you?",
    "Oh, not bad. Busy, but not bad. And you?",
    "Can't complain. Did you see the news today?",
    "I did. Strange times, aren't they?",
    "They are. Still, we muddle through.",
    "We do. Anyway, I'd better get on.",
)


class CannedProvider:
    """Stock replies in turn, so a run with `SIMILE_LLM=fake` never reaches Claude."""

    name = "canned"

    def __init__(self, replies: Sequence[str] = CANNED) -> None:
        self._replies = itertools.cycle(replies)

    def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        return FakeProvider([next(self._replies)]).stream(request)


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    fake = os.environ.get(FAKE_ENV) == "fake"
    app.state.llm = llm = LLMClient(CannedProvider() if fake else None)
    try:
        yield
    finally:
        await llm.aclose()
