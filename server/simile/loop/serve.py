import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette

from simile.app import create_app
from simile.behaviour.mind import create_behaviour
from simile.conversation import create_engine
from simile.llm import LLMClient
from simile.loop.playthrough import Canned
from simile.schema import PLAYER_ID
from simile.world import Point, movement_of
from simile.world.paths import Spot


def create_loop_app(start: Spot, scratch: Path | None = None, seed: int = 0) -> Starlette:
    """The server on `SIMILE_DB`'s world, on `Canned`, with the player at `start`, seeded."""
    app = create_app()
    started = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        llm = LLMClient(Canned())
        app.state.behaviour = create_behaviour(app, seed=seed)
        app.state.conversation = create_engine(app, seed=seed)
        try:
            async with started(app):
                app.state.llm = llm
                app.state.players.rng.seed(seed)
                movement_of(app).track(PLAYER_ID, Point(start.x, start.y, start.map))
                yield
        finally:
            await llm.aclose()
            if scratch is not None:
                shutil.rmtree(scratch, ignore_errors=True)

    app.router.lifespan_context = lifespan
    return app
