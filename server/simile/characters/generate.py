import random
import re
import unicodedata
from collections.abc import Collection, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from typing import Any

from simile.art.palette import PALETTE
from simile.characters.biography import (
    CRITIC,
    CRITIQUED,
    SYSTEM,
    WRITTEN,
    biography_model,
    critic_prompt,
    critique_model,
    prompt,
)
from simile.characters.brief import Brief
from simile.characters.novelty import Match, Novelty
from simile.characters.sheet import Look, Sheet, draw, split_name
from simile.characters.tables import Tables, Village, load_tables
from simile.characters.traits import derive_traits
from simile.characters.voice import accent_sentence, needs_recording
from simile.llm import LLMClient, Model
from simile.schema import (
    PLAYER_ID,
    Appearance,
    Arrival,
    Character,
    CharacterSource,
    CharacterVoice,
    Gender,
    Hook,
    PastMemory,
)

MAX_INTERESTS = 6
UNSPLIT = str.maketrans({"Đ": "D", "đ": "d", "Ł": "L", "ł": "l", "Ø": "O", "ø": "o", "ß": "ss"})
"""Letters that Unicode normalisation doesn't split into a plain letter and an accent."""


@dataclass(frozen=True)
class Suggestion:
    """A change the critic proposes to a player's character, which only the player applies."""

    field: str
    """The field, or an item in one, such as `past[2]`."""
    current: str
    suggested: str


@dataclass(frozen=True)
class Generated:
    character: Character
    suggestions: list[Suggestion] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    """What the critic changed or suggested, and why."""
    warnings: list[str] = field(default_factory=list)


class TooSimilar(Exception):
    def __init__(self, character: Character, match: Match) -> None:
        super().__init__(f"{character.name} is too close to {match.name} ({match.similarity:.2f})")
        self.character = character
        self.match = match


async def generate(
    llm: LLMClient,
    brief: Brief | None = None,
    *,
    rng: random.Random | None = None,
    village: Village | None = None,
    novelty: Novelty | None = None,
    taken: Collection[str] = (),
    model: str = Model.HAIKU,
    retries: int = 1,
    now: datetime | None = None,
    tables: Tables | None = None,
) -> Generated:
    """A whole character from whatever `brief` locks. Every stage keeps what's locked."""
    brief = brief or Brief()
    t = tables or load_tables()
    sheet = draw(rng or random.Random(), brief, village=village, tables=t)
    id = character_id(settle(brief, sheet, t)["name"], taken)
    return await write(
        llm, brief, sheet, id=id, novelty=novelty, model=model, retries=retries, now=now, tables=t
    )


async def reroll(
    llm: LLMClient,
    character: Character,
    *sections: str,
    rng: random.Random | None = None,
    novelty: Novelty | None = None,
    model: str = Model.HAIKU,
    retries: int = 1,
    now: datetime | None = None,
    tables: Tables | None = None,
) -> Generated:
    """Redo `sections` (see `brief.SECTIONS`) and keep the rest, even where it no longer fits,
    so reroll sections that depend on each other together."""
    brief = Brief.keeping(character, *sections)
    t = tables or load_tables()
    village = Village(names=set(split_name(character.name))) if "name" in sections else None
    sheet = draw(rng or random.Random(), brief, village=village, tables=t)
    result = await write(
        llm,
        brief,
        sheet,
        id=character.id,
        novelty=novelty,
        model=model,
        retries=retries,
        now=now,
        created=character.created,
        version=character.version + 1,
        tables=t,
    )
    if "name" in sections:
        return replace(result, character=renamed(result.character, character.name))
    return result


async def write(
    llm: LLMClient,
    brief: Brief,
    sheet: Sheet,
    *,
    id: str,
    novelty: Novelty | None = None,
    model: str = Model.HAIKU,
    retries: int = 1,
    now: datetime | None = None,
    created: datetime | None = None,
    version: int = 1,
    tables: Tables | None = None,
) -> Generated:
    """Claude's stages: the biography, the critic and the novelty check. A premade character too
    close to the library is written again; a player's only gets a warning."""
    t = tables or load_tables()
    now = now or datetime.now(UTC)
    facts = settle(brief, sheet, t)
    locks = brief.locks()
    wanted = [field for field in WRITTEN if field not in locks and _needed(field, sheet)]
    player = brief.source is CharacterSource.PLAYER
    checked = novelty is not None and (player or bool({"persona", "backstory"} & set(wanted)))
    avoid: str | None = None
    for attempt in range(retries + 1):
        written: dict[str, Any] = {}
        if wanted:
            reply = await llm.structured(
                prompt(facts, sheet, wanted, locks, t, avoid=avoid),
                biography_model(wanted, len(sheet.seeds()), len(sheet.hooks)),
                system=SYSTEM,
                model=model,
                purpose="character-biography",
            )
            written = {field: getattr(reply, field) for field in wanted}
        character = assemble(
            brief, sheet, facts, written, id=id, now=now, created=created, version=version
        )
        result = Generated(character)
        if set(wanted) & set(CRITIQUED):
            result = await _critique(llm, brief, sheet, facts, character, wanted, model, t)
        match = novelty.too_close(result.character) if novelty and checked else None
        if match is None:
            return result
        if player:
            warning = f"Close to {match.name} in the library ({match.similarity:.2f})."
            return replace(result, warnings=[warning])
        if attempt == retries:
            raise TooSimilar(result.character, match)
        avoid = f"{match.name}. {first_sentence(match.persona)}"
    raise AssertionError("unreachable")


def settle(brief: Brief, sheet: Sheet, tables: Tables) -> dict[str, Any]:
    """The fields decided in code, with whatever the brief locks."""
    s = sheet.skeleton
    arrival = None
    if not s.born_here and s.arrived_at is not None and s.arrival is not None:
        reason = next((a.text for a in tables.census.arrival if a.id == s.arrival), s.arrival)
        arrival = Arrival(age=s.arrived_at, reason=reason.removeprefix("came "))
    facts: dict[str, Any] = {
        "name": s.name,
        "birth_year": s.birth_year,
        "gender": Gender(s.gender),
        "origin": sheet.country,
        "arrival": arrival,
        "occupation": _title(s.occupation),
        "values": sheet.values,
        "traits": derive_traits(sheet.values, sheet.temperament),
    }
    return facts | {field: v for field, v in brief.locks().items() if field in facts}


def assemble(
    brief: Brief,
    sheet: Sheet,
    facts: Mapping[str, Any],
    written: Mapping[str, Any],
    *,
    id: str,
    now: datetime,
    created: datetime | None = None,
    version: int = 1,
) -> Character:
    made = dict(facts)
    texts = written.get("past", [])
    made["past"] = [
        PastMemory(age=seed.age, content=text, salience=seed.salience, valence=seed.valence)
        for seed, text in zip(sheet.seeds(), texts, strict=False)
    ]
    descriptions = written.get("hooks", [])
    made["hooks"] = [
        Hook(kind=kind, side=side, description=text)
        for (kind, side), text in zip(sheet.hooks, descriptions, strict=False)
    ]
    for name in ("backstory", "persona", "speaking_style", "craft"):
        if name in written:
            made[name] = written[name]
    made["mannerisms"] = sheet.mannerisms
    made["humour"] = sheet.humour
    if "interests" in written:
        made["interests"] = written["interests"][:MAX_INTERESTS]
    if appearance := written.get("appearance"):
        made["appearance"] = _with_look(appearance, sheet.look)
    if voice := written.get("voice"):
        made["voice"] = CharacterVoice(
            description=f"{accent_sentence(sheet.accent)} {voice.description}",
            reference_line=voice.reference_line,
            needs_recording=needs_recording(sheet.accent),
        )
    made |= brief.locks()
    return Character(
        id=id,
        **made,
        source=brief.source,
        created=created or now,
        updated=now,
        version=version,
    )


def character_id(name: str, taken: Collection[str] = ()) -> str:
    """A lowercase slug of their whole name, with a number added if it's taken."""
    plain = unicodedata.normalize("NFKD", name.translate(UNSPLIT)).encode("ascii", "ignore")
    slug = "_".join(re.findall(r"[a-z0-9]+", plain.decode().lower()))[:60] or "character"
    if not slug[0].isalpha():
        slug = f"c_{slug}"
    unavailable = {*taken, PLAYER_ID}
    candidate, suffix = slug, 2
    while candidate in unavailable:
        candidate, suffix = f"{slug}_{suffix}", suffix + 1
    return candidate


async def _critique(
    llm: LLMClient,
    brief: Brief,
    sheet: Sheet,
    facts: Mapping[str, Any],
    character: Character,
    wanted: Sequence[str],
    model: str,
    t: Tables,
) -> Generated:
    """A premade character's newly written text is revised; a player's comes back as
    suggestions, their own text included."""
    player = brief.source is CharacterSource.PLAYER
    draft = _critiqued(character)
    editable = [f for f in CRITIQUED if draft[f] and (player or f in wanted)]
    reply = await llm.structured(
        critic_prompt(facts, sheet, draft, editable, t),
        critique_model(editable, len(character.past), len(character.hooks)),
        system=CRITIC,
        model=model,
        purpose="character-critic",
    )
    revised = {f: getattr(reply, f) for f in editable}
    notes = list(getattr(reply, "notes", []))
    if player:
        return Generated(character, _suggestions(draft, revised), notes)
    return Generated(_revise(character, revised), [], notes)


def _critiqued(character: Character) -> dict[str, Any]:
    return {
        "backstory": character.backstory,
        "persona": character.persona,
        "speaking_style": character.speaking_style,
        "interests": list(character.interests),
        "past": [memory.content for memory in character.past],
        "hooks": [hook.description for hook in character.hooks],
    }


def _revise(character: Character, revised: Mapping[str, Any]) -> Character:
    data = character.model_dump()
    for name, value in revised.items():
        if name == "past":
            data["past"] = [m | {"content": c} for m, c in zip(data["past"], value, strict=False)]
        elif name == "hooks":
            data["hooks"] = [
                h | {"description": d} for h, d in zip(data["hooks"], value, strict=False)
            ]
        elif name == "interests":
            data[name] = value[:MAX_INTERESTS]
        else:
            data[name] = value
    return Character.model_validate(data)


def _suggestions(draft: Mapping[str, Any], revised: Mapping[str, Any]) -> list[Suggestion]:
    found = []
    for name, value in revised.items():
        if name in ("past", "hooks"):
            found += [
                Suggestion(f"{name}[{i}]", old, new)
                for i, (old, new) in enumerate(zip(draft[name], value, strict=False))
                if old != new
            ]
        elif value != draft[name]:
            join = "; ".join if isinstance(value, list) else str
            found.append(Suggestion(name, join(draft[name]), join(value)))
    return found


def renamed(character: Character, old: str) -> Character:
    """`character` with its new name wherever their `old` one slipped into their own prose."""
    new_given, old_given = split_name(character.name)[0], split_name(old)[0]

    def swap(text: str) -> str:
        text = text.replace(old, character.name)
        return re.sub(rf"\b{re.escape(old_given)}\b", new_given, text)

    data = character.model_dump()
    for name in ("backstory", "persona", "speaking_style"):
        data[name] = swap(data[name])
    data["past"] = [m | {"content": swap(m["content"])} for m in data["past"]]
    data["hooks"] = [h | {"description": swap(h["description"])} for h in data["hooks"]]
    return Character.model_validate(data)


def _with_look(appearance: Appearance, look: Look | None) -> Appearance:
    if look is None:
        return appearance
    top = PALETTE[look.top]
    return appearance.model_copy(
        update={"build": look.build, "hair_style": look.hair_style, "top_colour": top}
    )


def _needed(field: str, sheet: Sheet) -> bool:
    if field == "past":
        return bool(sheet.seeds())
    if field == "hooks":
        return bool(sheet.hooks)
    return True


def _title(occupation: str) -> str:
    for article in ("a ", "an "):
        occupation = occupation.removeprefix(article)
    return occupation[:1].upper() + occupation[1:]


def first_sentence(text: str) -> str:
    return re.split(r"(?<=[.!?])\s+", text.strip(), maxsplit=1)[0]
