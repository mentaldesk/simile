import logging
import random

from starlette.applications import Starlette

from simile.behaviour import behaviour_of
from simile.memory import memory_of
from simile.persistence import investigation_of
from simile.schema import Incident
from simile.sim import world_of
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.incident import make_incident

logger = logging.getLogger(__name__)


async def begin(
    app: Starlette, *, config: StoryConfig = DEFAULT_CONFIG, rng: random.Random | None = None
) -> Incident | None:
    """Make the world's incident if it has none: a new world, or one saved before there was an
    incident. It's saved before its memories are stored, so it's only ever made once. Returns
    the incident made, or None."""
    investigation = investigation_of(app)
    if investigation.incident is not None:
        return None
    clock = world_of(app).clock
    npcs = list(behaviour_of(app).npcs.values())
    logger.info("%s  Making the incident among %d residents", clock, len(npcs))
    made = await make_incident(
        npcs, clock.now, getattr(app.state, "llm", None), rng=rng, config=config
    )
    investigation.incident = made.incident
    if (saver := getattr(app.state, "persistence", None)) is not None:
        await saver.save()
    memory_of(app).add(*made.memories)
    logger.info(
        "%s  %s attacked Aris%s: %s",
        clock,
        ", ".join(made.incident.attackers),
        "" if made.written else " (motive from templates)",
        made.incident.motive,
    )
    return made.incident
