from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.jobs import jobs_of
    from simile.library import library_of
    from simile.voicelib import greetings
    from simile.voicelib.config import from_environment
    from simile.voicelib.kinds import CHECK_KIND, DESIGN_KIND, uploads_dir
    from simile.voicelib.uploads import remove_stale, waiting_of

    jobs = jobs_of(app)
    remove_stale(uploads_dir(jobs.root))
    greet = greetings.kind(library_of(app), from_environment())
    unregister = [jobs.register(kind) for kind in (DESIGN_KIND, CHECK_KIND, greet)]
    try:
        yield
    finally:
        await waiting_of(app).close(jobs)
        for undo in unregister:
            undo()
