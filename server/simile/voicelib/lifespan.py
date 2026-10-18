from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from starlette.applications import Starlette


@asynccontextmanager
async def lifespan(app: Starlette) -> AsyncIterator[None]:
    from simile.jobs import jobs_of
    from simile.voicelib.kinds import CHECK_KIND, DESIGN_KIND, uploads_dir
    from simile.voicelib.uploads import remove_stale

    jobs = jobs_of(app)
    remove_stale(uploads_dir(jobs.root))
    unregister = [jobs.register(DESIGN_KIND), jobs.register(CHECK_KIND)]
    try:
        yield
    finally:
        for undo in unregister:
            undo()
