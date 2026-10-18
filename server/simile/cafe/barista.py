import random
from collections.abc import Sequence

from pydantic import field_validator

from simile.llm import LLMClient, Model
from simile.npc.generate import SYSTEM, YOUNGEST, Brief, Draft, assemble, prompt
from simile.npc.values import POOL_SIZE, distance, sample_profile
from simile.schema import Craft, Medium, Npc

HOME = "coffee_shop"
OCCUPATION = "Barista at the Daily Grind"
OLDEST = 60

JOB = f"""

This resident is the Daily Grind's barista. Their occupation is "{OCCUPATION}", exactly as given, \
and they live in the flat above the shop. They work the counter from 07:00 to 17:00, so their \
history, persona and voice should fit someone who makes coffee and chats with the whole village \
every day. Their craft is writing or nothing, never murals."""


class BaristaDraft(Draft):
    @field_validator("craft")
    @classmethod
    def _no_murals(cls, craft: Craft | None) -> Craft | None:
        if craft is not None and craft.medium is Medium.MURAL:
            raise ValueError("the barista writes or makes nothing, never murals")
        return craft


def brief(others: Sequence[Npc], seed: int) -> Brief:
    """Values as far from every other resident's as N1's pool allows, an adult's age and a
    gender, all from the seed."""
    rng = random.Random(seed)
    pool = [sample_profile(rng) for _ in range(POOL_SIZE)]
    values = max(pool, key=lambda p: min((distance(p, o.values) for o in others), default=0.0))
    return Brief(HOME, rng.randint(YOUNGEST, OLDEST), rng.choice(("woman", "man")), values)


async def generate_barista(
    llm: LLMClient, others: Sequence[Npc], seed: int, *, model: str = Model.SONNET
) -> Npc:
    """N1's resident prompt, for one more resident who works the café's counter."""
    plan = brief(others, seed)
    count = len(others) + 1
    draft = await llm.structured(
        prompt(plan, count, count, others) + JOB,
        BaristaDraft,
        system=SYSTEM,
        model=model,
        purpose="generate-npc",
    )
    npc = assemble(plan, draft, {other.id for other in others})
    return npc.model_copy(update={"occupation": OCCUPATION})
