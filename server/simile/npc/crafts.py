from collections.abc import AsyncIterator, Sequence

from simile.llm import LLMClient, Model
from simile.npc.generate import CRAFT, VILLAGE, craft_label, values_brief
from simile.schema import Craft, Npc
from simile.schema import Model as Schema


class Choice(Schema):
    craft: Craft | None
    why: str


SYSTEM = f"""\
You choose crafts for the residents of {VILLAGE}

Every resident has a score from 0 to 1 for each of 24 core values. The values are the character, \
and their job, persona and interests follow from them. Their craft should too. Write in plain \
English with British spelling."""


def prompt(npc: Npc, others: Sequence[Npc]) -> str:
    crafts = "\n".join(f"- {n.name}, {n.occupation}: {craft_label(n.craft)}" for n in others)
    return f"""\
Choose a craft for {npc.name}, {npc.age}, {npc.occupation}.

{values_brief(npc.values)}

Persona: {npc.persona}

Interests: {"; ".join(npc.interests)}

Crafts so far. Give this one a different form from theirs:
{crafts or "- none yet"}

Write:
{CRAFT}
- why: one sentence on why this craft, or none, fits them."""


async def add_crafts(
    llm: LLMClient,
    npcs: Sequence[Npc],
    *,
    others: Sequence[Npc] = (),
    model: str = Model.SONNET,
) -> AsyncIterator[tuple[Npc, str]]:
    """Have Claude choose each resident's craft in turn, yielding each with why it fits."""
    crafted: list[Npc] = []
    for npc in npcs:
        choice = await llm.structured(
            prompt(npc, [*others, *crafted]),
            Choice,
            system=SYSTEM,
            model=model,
            purpose="npc-craft",
        )
        crafted.append(npc.model_copy(update={"craft": choice.craft}))
        yield crafted[-1], choice.why
