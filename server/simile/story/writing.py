import asyncio
import logging
from collections.abc import Sequence

from pydantic import BaseModel, Field

from simile.llm import LLMClient, LLMError, StructuredOutputError
from simile.npc.values import ranked
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.content import Place, StoryContent
from simile.story.suspects import Suspect

logger = logging.getLogger(__name__)

PURPOSE = "story-motive"

SYSTEM = """You write the hidden backstory of a village mystery game. The game has already \
decided who attacked Aris and roughly why. You write the specifics, which the residents will \
later voice: why they did it, and what each of them remembers and says.

Make it credible: concrete, specific to each attacker's life, job and values, and on a small \
village's scale, like a slight, a loss or a fear that festered. No cartoon villainy. They meant to \
frighten or punish her, not to kill her, and it went further than they meant. Don't invent other \
people, places or events beyond what the grievances need. Keep to the game's tone: no gore beyond \
what's given, no slurs. Plain, everyday English."""


class Written(BaseModel):
    """One attacker's side of it."""

    id: str = Field(description="The attacker's id, as given.")
    grievance: str = Field(
        min_length=1,
        max_length=320,
        description="What Aris did to them, in one sentence in the third person, naming them.",
    )
    resents: str = Field(
        min_length=1, max_length=320, description="The same, in one sentence in their own words."
    )
    remembers: str = Field(
        min_length=1,
        max_length=400,
        description="Their own memory of that night, in one or two sentences in the first "
        "person, as they'd put it to themselves.",
    )
    alibi: str = Field(
        min_length=1,
        max_length=160,
        description="What they tell anyone who asks where they were that night, in their own "
        "voice: one short sentence.",
    )
    deflection: str = Field(
        min_length=1,
        max_length=160,
        description="What they say if asked who attacked Aris, in their own voice: one short "
        "sentence.",
    )
    denial: str = Field(
        min_length=1,
        max_length=160,
        description="What they say if asked how they got on with Aris, in their own voice: one "
        "short sentence.",
    )
    note: str = Field(
        min_length=1,
        max_length=240,
        description="A line Aris wrote in her workshop notebook a day or two before, about "
        "them and their grievance, in her voice, naming them only by their initial.",
    )


class Backstory(BaseModel):
    motive: str = Field(
        min_length=1,
        max_length=900,
        description="Why they attacked her, in two or three sentences in the third person and "
        "the past tense. With several attackers, what brought them together.",
    )
    attackers: list[Written] = Field(description="One for each attacker, in the order given.")


def prompt(suspects: Sequence[Suspect], content: StoryContent, met: Place | None = None) -> str:
    aris = content.aris
    together = (
        f"The {len(suspects)} of them went together." if len(suspects) > 1 else "They went alone."
    )
    if len(suspects) > 1 and met is not None:
        together += (
            f" They met at {met.name} the evening before and talked about sorting out the maker "
            "space once and for all."
        )
    people = "\n".join(_described(found, content) for found in suspects)
    return (
        f"Aris: {aris.description}\n\n"
        "The night: someone smashed up her workshop, the maker space, and attacked her in the "
        "lane behind it, tearing her steel hand half off. She survived and wouldn't say who did "
        "it. A week later her workshop was found standing open, her tea cold, and she hasn't "
        "been seen since. Nobody official has come asking.\n\n"
        f"Who attacked her:\n{people}\n\n{together}\n\n"
        "Write the motive, and each attacker's side of it."
    )


def _described(found: Suspect, content: StoryContent) -> str:
    npc = found.npc
    order = [value.value.replace("_", " ") for value, _ in ranked(npc.values)]
    most, least = ", ".join(order[:4]), ", ".join(reversed(order[-3:]))
    persona = npc.persona.split(". ")[0].rstrip(".")
    return (
        f"- {npc.id}: {npc.name}, {npc.age}, {npc.occupation}. {persona}. Cares most about "
        f"{most}; least about {least}. Their initial: {initial(npc.name)} What Aris did: "
        f"{content.grievances[found.grievance].told}"
    )


def initial(name: str) -> str:
    return f"{name[0].upper()}."


def drafted(suspects: Sequence[Suspect], content: StoryContent) -> Backstory:
    """The backstory from the content's templates, for when nobody writes it."""
    texts = content.texts
    names = [found.npc.name.split()[0] for found in suspects]
    sides = []
    for found, name in zip(suspects, names, strict=True):
        grievance = content.grievances[found.grievance]
        others = [other for other in names if other != name]
        sides.append(
            Written(
                id=found.npc.id,
                grievance=grievance.grievance.format(name=name),
                resents=grievance.resents,
                remembers=texts.remembers.replace(
                    "{with}", f" with {' and '.join(others)}" if others else ""
                ),
                alibi=texts.alibi,
                deflection=texts.deflection,
                denial=texts.denial,
                note=grievance.note.format(initial=initial(found.npc.name)[0]),
            )
        )
    end = texts.alone.format(name=names[0]) if len(names) == 1 else texts.together
    motive = " ".join([*(side.grievance for side in sides), end])
    return Backstory(motive=motive, attackers=sides)


async def write(
    llm: LLMClient | None,
    suspects: Sequence[Suspect],
    content: StoryContent,
    config: StoryConfig = DEFAULT_CONFIG,
    *,
    met: Place | None = None,
) -> tuple[Backstory, bool]:
    """The backstory, written with one `structured` call, and whether it was, with several
    attackers having `met` beforehand. Anything it leaves out, or a call that fails, falls back
    to the templates."""
    fallback = drafted(suspects, content)
    if llm is None:
        return fallback, False
    try:
        async with asyncio.timeout(config.write_for):
            written = await llm.structured(
                prompt(suspects, content, met),
                Backstory,
                system=SYSTEM,
                model=config.model,
                purpose=PURPOSE,
            )
    except (LLMError, StructuredOutputError, TimeoutError) as error:
        logger.warning("Couldn't write the incident's motive, so it's from templates: %s", error)
        return fallback, False
    sides = {side.id: side for side in written.attackers}
    return (
        Backstory(
            motive=written.motive,
            attackers=[sides.get(side.id, side) for side in fallback.attackers],
        ),
        True,
    )
