from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette

from simile.llm.client import LLMClient


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    app.state.llm = LLMClient()
    yield
