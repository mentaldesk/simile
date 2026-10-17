import random
import re
import unicodedata
from collections.abc import AsyncIterator, Collection, Sequence
from dataclasses import dataclass

from pydantic import Field, field_validator

from simile.art.characters import SKIN_TONES
from simile.art.palette import PALETTE, hex_to_rgb, nearest
from simile.llm import LLMClient, Model
from simile.npc.values import Profile, format_scores, ranked, sample_values
from simile.schema import PLAYER_ID, Appearance, CoreValue, Craft, Npc, Voice
from simile.schema import Model as Schema

HOMES = tuple(f"house_{n}" for n in range(1, 11))
YOUNGEST, OLDEST = 19, 80
STABILITY = (CoreValue.TRADITION, CoreValue.SECURITY, CoreValue.OBEDIENCE)
NOVELTY = (CoreValue.ADVENTURE, CoreValue.FREEDOM, CoreValue.PLEASURE)
MIN_WORDS, MAX_WORDS = 12, 25


@dataclass(frozen=True)
class Brief:
    """What's decided in code before Claude writes the character."""

    home: str
    age: int
    gender: str
    values: Profile


def plan(count: int, seed: int) -> list[Brief]:
    if not 1 <= count <= len(HOMES):
        raise ValueError(f"count must be 1-{len(HOMES)}, one per home")
    rng = random.Random(seed)
    profiles = sample_values(count, rng)
    ages = _ages(profiles, rng)
    genders = [("woman", "man")[i % 2] for i in range(count)]
    rng.shuffle(genders)
    return [
        Brief(home, age, gender, profile)
        for home, age, gender, profile in zip(HOMES, ages, genders, profiles, strict=False)
    ]


def _ages(profiles: Sequence[Profile], rng: random.Random) -> list[int]:
    """Spread across adulthood, older for those who value stability over novelty."""
    settled = [
        sum(p[v] for v in STABILITY) - sum(p[v] for v in NOVELTY) + rng.gauss(0, 0.5)
        for p in profiles
    ]
    band = (OLDEST - YOUNGEST + 1) / len(profiles)
    ages = [0] * len(profiles)
    for rank, i in enumerate(sorted(range(len(profiles)), key=settled.__getitem__)):
        low = YOUNGEST + round(rank * band)
        ages[i] = rng.randint(low, max(low, YOUNGEST + round((rank + 1) * band) - 1))
    return ages


class Draft(Schema):
    name: str
    occupation: str
    backstory: str
    persona: str
    speaking_style: str
    interests: list[str] = Field(min_length=3, max_length=6)
    craft: Craft | None
    voice_description: str
    reference_line: str
    appearance: Appearance

    @field_validator("reference_line")
    @classmethod
    def _neutral_and_short(cls, line: str) -> str:
        words = len(line.split())
        if not MIN_WORDS <= words <= MAX_WORDS:
            raise ValueError(
                f"must be {MIN_WORDS}-{MAX_WORDS} words (5-10 seconds of speech), not {words}"
            )
        if "!" in line:
            raise ValueError("must be delivered neutrally, without exclamation marks")
        return line


VILLAGE = """\
Simile, a simulation of a small village in 2026 with a slightly futuristic feel, like a quiet \
corner of Shenzhen: delivery drones overhead, solar roofs, public news terminals. It has a coffee \
shop (The Daily Grind), a town square, a noodle bar, a maker space and a riverside park. The \
residents talk to each other and to the player, out loud, each in their own voice."""

SYSTEM = f"""\
You create residents for {VILLAGE}

Every resident has a score from 0 to 1 for each of 24 core values. The values are the character. \
Their job, history, persona, way of speaking, interests, looks and voice all follow from what \
they care about most and least, so that a reader could guess their top values from any one of \
them. Write grounded, specific, contemporary people rather than fantasy archetypes, in plain \
English with British spelling."""


CRAFT = """\
- craft: what they make in their own time, which can differ from their job, or null if they make \
nothing. Its medium is "writing", which goes up on the public news terminals beside the news, or \
"mural", painted on one of the few walls around town. Each work starts from whatever is on their \
mind, such as news they've read or a conversation they've had, and says something about it in \
line with their values, taking a side where they care strongly. So a craft is how they have their \
say in public, in a style that suits them, and a neighbour should be able to guess the maker from \
the work. Its form names the kind of work, and its subject or slant if that's part of it, in two \
to six words, such as "political street murals", "plain verse about the river" or "stern notices \
for the residents' board". Most residents have one, but someone with little creativity and \
nothing they want to say may have none."""


def values_brief(values: Profile) -> str:
    order = ranked(values)
    return f"""\
Core values (0 = indifferent, 1 = central to who they are):
- Cares most about: {format_scores(order[:5])}
- Cares least about: {format_scores(order[::-1][:5])}
- All 24: {format_scores(list(values.items()))}"""


def craft_label(craft: Craft | None) -> str:
    return f"{craft.medium}: {craft.form}" if craft else "none"


def prompt(brief: Brief, number: int, count: int, others: Sequence[Npc]) -> str:
    residents = "\n".join(
        f"- {n.name}, {n.age}, {n.occupation}. {first_sentence(n.backstory)} {_look(n)} "
        f"Craft: {craft_label(n.craft)}."
        for n in others
    )
    skins = ", ".join(PALETTE[name] for name in SKIN_TONES)
    palette = ", ".join(f"{name} {colour}" for name, colour in PALETTE.items())
    return f"""\
Create resident {number} of {count}.

Fixed facts:
- Age: {brief.age}
- Gender: {brief.gender}

{values_brief(brief.values)}

Residents so far. Give this one a different first name, surname, occupation, background and \
craft, and a look that's easy to tell apart from theirs at sprite size:
{residents or "- none yet"}

Write:
- name: a first and last name. The village is international.
- occupation: a short job title, two to five words, for work someone with these values would \
choose or end up in, done in or from the village.
- backstory: two or three sentences on how their strongest values formed and why they live here.
- persona: two or three sentences. The first sums them up in one line. Show the top values in how \
they behave, and the bottom ones in what they ignore or dismiss.
- speaking_style: one or two sentences on pace, formality, vocabulary and verbal habits, \
following from their values and age. For example, high discipline and tradition: measured and \
formal; high adventure and optimism: quick and bright; high compassion and connection: warm, \
asks about you; high knowledge: precise, explains things.
- interests: three to six short topics they bring up in conversation, driven by their values.
{CRAFT}
- voice_description: for a text-to-speech voice design model. Start with gender and age \
("A woman in her late sixties."), then pitch, timbre, pace and manner, shaped by age and values \
like the speaking style. Describe only the sound, in 25-50 words, without names.
- reference_line: one or two sentences, {MIN_WORDS}-{MAX_WORDS} words (5-10 seconds of speech), \
that they might say on an ordinary day, in character. It is recorded once and its tone carries \
into everything they ever say, so it must be calm and neutral in delivery: a plain statement, \
no exclamation marks, no question, no strong emotion, no laughter, no other residents' names.
- appearance: their pixel-art sprite, fitting their age, job and personality. Skin is one of \
{skins}. Other colours come from this palette: {palette}. Choose zero to two accessories that \
suit them, such as an apron for food work, a cap for outdoor work or a scarf for someone who \
dresses with care."""


def _look(npc: Npc) -> str:
    a = npc.appearance
    hair, top, bottom = (
        nearest(hex_to_rgb(c)) for c in (a.hair_colour, a.top_colour, a.bottom_colour)
    )
    accessories = ", ".join(a.accessories) or "no accessories"
    clothes = f"{top} top, {bottom} bottoms"
    return f"Looks: {a.build} build, {a.hair_style} {hair} hair, {clothes}, {accessories}."


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]


def npc_id(name: str, taken: Collection[str]) -> str:
    """A lowercase slug of their first name, or more of their name if that's taken."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    words = re.findall(r"[a-z0-9]+", ascii_name.lower()) or ["npc"]
    if not words[0][0].isalpha():
        words.insert(0, "npc")
    unavailable = {*taken, PLAYER_ID}
    for length in range(1, len(words) + 1):
        if (candidate := "_".join(words[:length])[:60]) not in unavailable:
            return candidate
    suffix = 2
    while f"{candidate}_{suffix}" in unavailable:
        suffix += 1
    return f"{candidate}_{suffix}"


def assemble(brief: Brief, draft: Draft, taken: Collection[str]) -> Npc:
    return Npc(
        id=npc_id(draft.name, taken),
        name=draft.name,
        age=brief.age,
        occupation=draft.occupation,
        home=brief.home,
        values=brief.values,
        backstory=draft.backstory,
        persona=draft.persona,
        speaking_style=draft.speaking_style,
        interests=draft.interests,
        appearance=draft.appearance,
        voice=Voice(description=draft.voice_description, reference_line=draft.reference_line),
        craft=draft.craft,
    )


async def generate(
    llm: LLMClient, count: int, seed: int, *, model: str = Model.SONNET
) -> AsyncIterator[Npc]:
    """Plan the village from the seed, then have Claude write each resident in turn."""
    npcs: list[Npc] = []
    for number, brief in enumerate(plan(count, seed), start=1):
        draft = await llm.structured(
            prompt(brief, number, count, npcs),
            Draft,
            system=SYSTEM,
            model=model,
            purpose="generate-npc",
        )
        npcs.append(assemble(brief, draft, {npc.id for npc in npcs}))
        yield npcs[-1]
