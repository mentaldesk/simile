import logging
import random

from starlette.applications import Starlette

from simile.behaviour import behaviour_of
from simile.casting.store import load_cast
from simile.memory import memory_of
from simile.persistence import investigation_of
from simile.schema import Disappearance, Investigation, JournalEntry
from simile.sim import world_of
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.disappearance import logged, make_disappearance
from simile.story.town import PREFIX

logger = logging.getLogger(__name__)


async def begin(
    app: Starlette, *, config: StoryConfig = DEFAULT_CONFIG, rng: random.Random | None = None
) -> Disappearance | None:
    """Make the world's disappearance if it has none, storing its memories before saving it."""
    investigation = investigation_of(app)
    saver = getattr(app.state, "persistence", None)
    if investigation.disappearance is not None:
        if logged(investigation.disappearance) and saver is not None:
            await saver.save()
        return None
    clock, memory = world_of(app).clock, memory_of(app)
    if left := memory.forget_facts():
        logger.warning("%s  Forgot %d memories of a story that was never saved", clock, left)
    npcs = list(behaviour_of(app).npcs.values())
    if not npcs:
        return None
    if rng is None:
        cast = load_cast()
        rng = random.Random(f"story/{cast.seed}") if cast is not None else random.Random()
    made = make_disappearance(npcs, clock.now, rng=rng, config=config)
    still_true(investigation, made.disappearance)
    memory.add(*made.memories)
    investigation.disappearance = made.disappearance
    if saver is not None:
        await saver.save()
    logger.info("%s  Made the disappearance", clock)
    return made.disappearance


def still_true(investigation: Investigation, disappearance: Disappearance) -> None:
    """Keeps the town's entries and those still true word for word, and leads to facts left."""
    facts = {fact.id: fact for fact in disappearance.facts}

    def kept(entry: JournalEntry) -> bool:
        fact = facts.get(entry.fact_id)
        return entry.fact_id.startswith(PREFIX) or (fact is not None and fact.what == entry.text)

    def exists(fact_id: str) -> bool:
        return fact_id in facts or fact_id.startswith(PREFIX)

    journal = [entry for entry in investigation.journal if kept(entry)]
    for entry in journal:
        entry.leads = [lead for lead in entry.leads if exists(lead.fact_id)]
    investigation.journal = journal
