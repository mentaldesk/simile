import logging
import random

from starlette.applications import Starlette

from simile.behaviour import behaviour_of
from simile.casting.store import load_cast
from simile.memory import memory_of
from simile.persistence import investigation_of
from simile.schema import Incident
from simile.sim import world_of
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.incident import logged, make_incident

logger = logging.getLogger(__name__)


async def begin(
    app: Starlette, *, config: StoryConfig = DEFAULT_CONFIG, rng: random.Random | None = None
) -> Incident | None:
    """Make the world's incident if it has none, storing its memories before saving it."""
    investigation = investigation_of(app)
    saver = getattr(app.state, "persistence", None)
    if investigation.incident is not None:
        if logged(investigation.incident) and saver is not None:
            await saver.save()
        return None
    clock, memory = world_of(app).clock, memory_of(app)
    if left := memory.forget_facts():
        logger.warning("%s  Forgot %d memories of an incident that was never saved", clock, left)
    npcs = list(behaviour_of(app).npcs.values())
    if not npcs:
        return None
    if rng is None:
        cast = load_cast()
        rng = random.Random(f"story/{cast.seed}") if cast is not None else random.Random()
    llm = getattr(app.state, "llm", None)
    made = await make_incident(npcs, clock.now, llm, rng=rng, config=config)
    memory.add(*made.memories)
    investigation.incident = made.incident
    if saver is not None:
        await saver.save()
    logger.info("%s  Made the incident%s", clock, "" if made.written else " from templates")
    return made.incident
