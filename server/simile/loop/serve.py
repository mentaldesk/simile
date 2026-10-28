import shutil
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from starlette.applications import Starlette

from simile.app import create_app
from simile.behaviour.mind import create_behaviour
from simile.conversation import create_engine
from simile.llm import LLMClient
from simile.loop.playthrough import Covers, alibis
from simile.persistence import investigation_of
from simile.schema import PLAYER_ID
from simile.world import Point, movement_of
from simile.world.paths import Spot


def create_loop_app(start: Spot, scratch: Path | None = None, seed: int = 0) -> Starlette:
    """The server on `SIMILE_DB`'s world, with `Covers`, the player at `start`, and residents who
    choose by `seed`, so a beat's world plays out the same each time it's served."""
    app = create_app()
    started = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app: Starlette) -> AsyncIterator[None]:
        covers = Covers({})
        llm = LLMClient(covers)
        app.state.behaviour = create_behaviour(app, seed=seed)
        app.state.conversation = create_engine(app, seed=seed)
        try:
            async with started(app):
                covers.alibis.update(alibis(investigation_of(app).incident))
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
