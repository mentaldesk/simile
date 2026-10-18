import re
from collections.abc import Mapping, Sequence
from typing import Annotated, Any

from pydantic import AfterValidator, Field, create_model

from simile.art.characters import SKIN_TONES
from simile.art.palette import PALETTE
from simile.characters.sheet import Sheet
from simile.characters.tables import YEAR, Tables, describe_temperament
from simile.npc.values import format_scores, ranked
from simile.schema import Appearance, Arrival, Craft, HookKind, HookSide
from simile.schema import Model as Schema

H, S = HookKind, HookSide

MIN_WORDS, MAX_WORDS = 12, 25
WRITTEN = (
    "backstory",
    "persona",
    "speaking_style",
    "interests",
    "craft",
    "past",
    "hooks",
    "voice",
    "appearance",
)
"""The fields Claude writes. Everything else is decided in code."""
CRITIQUED = ("backstory", "persona", "speaking_style", "interests", "past", "hooks")
PRONOUNS = {"woman": "she", "man": "he", "nonbinary": "they"}

HOOKS: dict[tuple[HookKind, HookSide], str] = {
    (H.ESTRANGED_SIBLING, S.MUTUAL): "a brother or sister they no longer speak to",
    (H.EX_PARTNER, S.MUTUAL): "an ex-partner",
    (H.OLD_FRIEND, S.MUTUAL): "an old friend from before",
    (H.RIVAL, S.MUTUAL): "a rival",
    (H.DEBT, S.ACTOR): "someone they borrowed money from and still owe",
    (H.DEBT, S.TARGET): "someone who borrowed money from them and still owes it",
    (H.SECRET, S.ACTOR): "someone who saw them do something they want kept hidden",
    (H.SECRET, S.TARGET): "someone they saw do something that person wants kept hidden",
    (H.BETRAYAL, S.ACTOR): "someone they betrayed",
    (H.BETRAYAL, S.TARGET): "someone who betrayed them",
    (H.SAVED_LIFE, S.ACTOR): "someone whose life they saved",
    (H.SAVED_LIFE, S.TARGET): "someone who saved their life",
}

NUMBER = (
    r"\d{1,2}|(?:twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:-\w+)?|ten|eleven"
    r"|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen"
)
AGES = re.compile(
    rf"\b(?:at|aged)\s+(?:{NUMBER})\b(?!\s*(?:am|pm|o'clock|in the|every|sharp|%|percent))"
    rf"|\bwhen (?:she|he|they) (?:was|were) (?:{NUMBER})\b",
    re.IGNORECASE,
)


def _reference_line(line: str) -> str:
    words = len(line.split())
    if not MIN_WORDS <= words <= MAX_WORDS:
        raise ValueError(f"must be {MIN_WORDS}-{MAX_WORDS} words, not {words}")
    if "!" in line:
        raise ValueError("must be delivered neutrally, without exclamation marks")
    return line


class VoiceDraft(Schema):
    description: str = Field(min_length=1)
    reference_line: Annotated[str, AfterValidator(_reference_line)]


def biography_model(wanted: Sequence[str], memories: int, hooks: int) -> type[Schema]:
    """A reply model with only the fields Claude is asked to write."""
    specs: dict[str, Any] = {
        "backstory": (str, Field(min_length=1)),
        "persona": (str, Field(min_length=1)),
        "speaking_style": (str, Field(min_length=1)),
        "interests": (list[str], Field(min_length=1)),
        "craft": (Craft | None, ...),
        "past": (list[str], Field(min_length=memories)),
        "hooks": (list[str], Field(min_length=hooks)),
        "voice": (VoiceDraft, ...),
        "appearance": (Appearance, ...),
    }
    return create_model("Biography", __base__=Schema, **{f: specs[f] for f in wanted})


def critique_model(editable: Sequence[str], memories: int, hooks: int) -> type[Schema]:
    specs: dict[str, Any] = {
        "notes": (list[str], Field(description="What you changed and why, a line each.")),
        "backstory": (str, Field(min_length=1)),
        "persona": (str, Field(min_length=1)),
        "speaking_style": (str, Field(min_length=1)),
        "interests": (list[str], Field(min_length=1)),
        "past": (list[str], Field(min_length=memories)),
        "hooks": (list[str], Field(min_length=hooks)),
    }
    return create_model("Critique", __base__=Schema, **{f: specs[f] for f in ("notes", *editable)})


def age_mentions(text: str) -> int:
    """How many times prose gives someone's age, as in "at 26" or "when she was forty"."""
    return len(AGES.findall(text))


SYSTEM = """\
You write characters for a library that a life-simulation game casts its villagers from. Each \
is a grounded, specific, contemporary person who could be cast into any small village in 2026, \
so never name or describe the village, its places or its other residents.

The facts in each brief were sampled from real-world distributions so the library is varied. \
They are settled: make them into one coherent life. A brief holds more than any one piece of \
writing needs, so use the facts that matter and leave the rest out. Where a fact sits oddly with \
the rest, that friction is part of who they are. Don't smooth anyone into a nice, articulate, \
consistent type: let their contradiction, wound, secret and want show in how they behave.

Write plain English with British spelling. Be concrete: name the actual job, object, habit or \
place, not an abstract quality. Avoid stock phrases such as "a testament to", "never looked \
back", "heart of gold", "wry smile", "quiet strength", "found solace", "journey" and "tapestry"."""

CRITIC = """\
You edit characters for a library that a life-simulation game casts its villagers from. Each \
was drafted from a brief of sampled facts. Find what is clichéd, generic or templated in the \
draft and replace it with something specific to this person.

Look hardest for:
- a backstory that walks through events in order, especially with ages ("at 26... at 31..."). \
Rebuild it around what mattered most, with no ages.
- stock phrases and stock types: the gruff one with a soft heart, the free spirit, the \
perfectionist who learns to let go.
- telling rather than showing: "she is generous" instead of what she does.
- smoothing: a person made nicer, more articulate or more consistent than the brief. Keep their \
edges, their contradiction and their secret.
- facts from the brief listed rather than used: "he has two siblings and a degree".
- memories that sound alike, or that aren't in the first person.
- a tie that says whether the other person is a man or a woman, their age or their job. Casting \
decides who they are, so take that out.
- vague interests such as "reading" or "music", or long ones: each is a short topic.
- facts bent away from the brief, such as a working person described as retired.

Never contradict the brief, but the prose needn't mention every fact in it: cut any that are \
only there because the brief listed them. Change only what needs it, keep each field about the \
same length, and never use their name in the prose. Return every field you're asked to edit, \
unchanged where it's fine."""


def describe(facts: Mapping[str, Any], sheet: Sheet, t: Tables) -> str:
    """The brief: every settled fact about them, for both the writer and the critic."""
    s = sheet.skeleton
    census = t.census
    age = YEAR - int(facts["birth_year"])
    pronoun = PRONOUNS[str(facts["gender"])]
    arrival: Arrival | None = facts["arrival"]
    origin = (
        f"born in {facts['origin']}, came here at {arrival.age} {arrival.reason}"
        if arrival
        else f"born here, to a family from {facts['origin']}"
    )
    siblings = {0: "no siblings", 1: "one sibling"}.get(s.siblings, f"{s.siblings} siblings")
    children = {0: "no children", 1: "one child"}.get(s.children, f"{s.children} children")
    order = ranked(facts["values"])
    temperament = "; ".join(describe_temperament(sheet.temperament, tables=t)[:5])
    attachment = _text(t.temperament.attachment, sheet.attachment)
    lines = [
        f"- Name: {facts['name']}. Refer to them as {pronoun}, never by name, so it can change.",
        f"- Gender: {facts['gender']}. Born {facts['birth_year']}, so {age} now.",
        f"- Origin: {origin}.",
        f"- Childhood: {_text(census.background, s.background)}, "
        f"{_text(census.upbringing, s.upbringing)}: {s.household}. {siblings.capitalize()}.",
        f"- Education: {_text(census.education, s.education)}.",
        f"- Now: {_text(census.partnership, s.partnership)}, {children}.",
        f"- Work: {facts['occupation']}.",
        f"- Cares most about: {format_scores(order[:5])}.",
        f"- Cares least about: {format_scores(order[::-1][:5])}.",
        f"- Temperament: {temperament or 'about average in every way'}.",
        f"- With people close to them: {attachment}.",
    ]
    if s.health != "none":
        lines.append(f"- Health: {_text(census.health.condition, s.health)}.")
    if sheet.mannerisms:
        lines.append(f"- Verbal habits: {'; '.join(sheet.mannerisms)}.")
    tension = sheet.tension
    if tension.wound:
        lines.append(f"- Wound: {tension.wound.text}.")
    if tension.secret:
        lines.append(f"- Secret, kept from everyone around them: {tension.secret.text}.")
    if tension.want:
        lines.append(f"- Wants {tension.want.want}, but needs {tension.want.need}.")
    return "\n".join(lines)


def prompt(
    facts: Mapping[str, Any],
    sheet: Sheet,
    wanted: Sequence[str],
    locked: Mapping[str, Any],
    t: Tables,
    *,
    avoid: str | None = None,
) -> str:
    sections = [f"Character brief:\n{describe(facts, sheet, t)}"]
    if "past" in wanted:
        seeds = enumerate(sheet.seeds(), 1)
        listed = "\n".join(f"{n}. At {seed.age}: {seed.text}" for n, seed in seeds)
        sections.append(
            "What happened to them. The ages are for the memories only: the backstory doesn't "
            f"give them.\n{listed}"
        )
    elif past := locked.get("past"):
        sections.append("Their memories:\n" + "\n".join(f"- At {m.age}: {m.content}" for m in past))
    if "hooks" in wanted:
        ties = "\n".join(f"{n}. {HOOKS[hook]}" for n, hook in enumerate(sheet.hooks, 1))
        sections.append(
            "Ties to people who may turn up in their life again, whoever they turn out to be:\n"
            + ties
        )
    if written := {f: v for f, v in locked.items() if f in WRITTEN and f != "past"}:
        sections.append(
            "Already written. Keep it as it is and make everything else fit it:\n"
            + "\n".join(f"- {field}: {_show(value)}" for field, value in written.items())
        )
    if avoid:
        sections.append(
            f"A first draft came out too close to a character already in the library: {avoid} "
            "Make this one clearly different in temperament, voice and the shape of their life."
        )
    instructions = "\n".join(f"- {field}: {INSTRUCTIONS[field](sheet)}" for field in wanted)
    sections.append(f"Write:\n{instructions}")
    return "\n\n".join(sections)


def critic_prompt(
    facts: Mapping[str, Any],
    sheet: Sheet,
    draft: Mapping[str, Any],
    editable: Sequence[str],
    t: Tables,
) -> str:
    shown = "\n".join(f"- {field}: {_show(draft[field])}" for field in CRITIQUED if field in draft)
    problems = []
    if (ages := age_mentions(str(draft.get("backstory", "")))) >= 2:
        problems.append(
            f"The backstory gives an age {ages} times. Rebuild it around what mattered, not as a "
            "timeline, with no ages."
        )
    notes = "\n".join(f"- {p}" for p in problems)
    return "\n\n".join(
        part
        for part in (
            f"Character brief:\n{describe(facts, sheet, t)}",
            f"The draft:\n{shown}",
            f"Already found:\n{notes}" if notes else "",
            f"Edit: {', '.join(editable)}. Keep lists the same length and in the same order.",
        )
        if part
    )


def _text(rows: Sequence[Any], id: str, missing: str | None = None) -> str:
    found = next((row.text for row in rows if row.id == id), None)
    return found or missing or id


def _show(value: Any) -> str:
    if isinstance(value, Schema):
        return value.model_dump_json()
    if isinstance(value, list):
        return "; ".join(_show(item) for item in value)
    return str(value)


def _past(sheet: Sheet) -> str:
    return (
        f"exactly {len(sheet.seeds())} memories, one for each thing that happened above and in "
        "the same order. Each is one or two sentences in the first person, in their own words, "
        "as they'd tell it now, built on one concrete detail rather than a summary. Never state "
        "the age, and vary how they start."
    )


def _hooks(sheet: Sheet) -> str:
    return (
        f"exactly {len(sheet.hooks)} sentences, one for each tie above and in the same order: the "
        "tie from their side, specific about what happened. Casting decides who the other person "
        "is, so never name them or say whether they're a man or a woman, their age or their job. "
        "A tie about something hidden can be about their secret."
    )


def _appearance(sheet: Sheet) -> str:
    skins = ", ".join(PALETTE[name] for name in SKIN_TONES)
    palette = ", ".join(f"{name} {colour}" for name, colour in PALETTE.items())
    fixed = ""
    if look := sheet.look:
        fixed = (
            f" Their build is {look.build}, their hair style {look.hair_style} and their top "
            f"{look.top} {PALETTE[look.top]}: use those."
        )
    return (
        "their pixel-art sprite, fitting their age, origin, work and personality. Skin is one of "
        f"{skins}. Other colours come from this palette: {palette}.{fixed} Choose zero to two "
        "accessories that suit them."
    )


INSTRUCTIONS = {
    "backstory": lambda sheet: (
        "who they are and how they got here, in 120 to 180 words. Build it around what made "
        "them: the wound, the contradiction and the want, not a timeline. Don't walk through "
        "the events in order and give no ages. Open on something specific about them, never on "
        "where they were born or grew up. Don't list facts from the brief, such as siblings, "
        "qualifications or where they came from: use one only where it matters. State the "
        "secret plainly: this is for the game, not for other characters."
    ),
    "persona": lambda sheet: (
        "two or three sentences, at most 70 words, on how they come across now. Show their top "
        "values in what they do and their bottom ones in what they ignore or dismiss. Show the "
        "wound and the want in behaviour without naming them. Keep their edges."
    ),
    "speaking_style": lambda sheet: (
        "one or two sentences on pace, formality, vocabulary and verbal habits, shaped by their "
        "temperament, values and age. It can build on a verbal habit from the brief, but don't "
        "just repeat it."
    ),
    "interests": lambda sheet: (
        "three to six short topics they bring up, two to five words each and specific, such as "
        '"chillies on the windowsill" rather than "gardening".'
    ),
    "craft": lambda sheet: (
        'what they make in their own time, or null if nothing. Its medium is "writing", put up '
        'for the neighbours to read, "mural", painted on a wall, or "painting", hung in the '
        'village gallery. Its form names the work in two to six words, such as "plain verse '
        'about the river". Many people make nothing.'
    ),
    "past": _past,
    "hooks": _hooks,
    "voice": lambda sheet: (
        'description: for a voice design model, 20 to 40 words. Start with gender and age ("A '
        "man in his early sixties.\"), then pitch, timbre, pace and manner. Don't name the "
        "accent: it goes in front of this. reference_line: one or two sentences, "
        f"{MIN_WORDS} to {MAX_WORDS} words, something they'd say about their own work, interests "
        "or day (not tea, kettles or the weather), in their own idiom. Calm and neutral in "
        "delivery: a plain statement, no exclamation mark, no question, no names. It's recorded "
        "once, so use words with plenty of varied sounds."
    ),
    "appearance": _appearance,
}
