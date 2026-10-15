import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.memory import SharedHistory
from simile.schema import CoreValue, FlagKind, Id, Line, Memory, Npc, Relationship
from simile.social import describe


class Cue(StrEnum):
    """What the line being written is for."""

    OPEN = "open"
    REPLY = "reply"
    GOODBYE = "goodbye"
    FAREWELL = "farewell"


CUES: dict[Cue, str] = {
    Cue.OPEN: "You've just walked up to {other}. Say hello and start the conversation.",
    Cue.REPLY: "Say your next line to {other}.",
    Cue.GOODBYE: "You've had enough of this conversation. Wrap it up now with a brief, natural "
    "goodbye to {other}.",
    Cue.FAREWELL: "{other} is leaving. Say a brief goodbye back.",
}

THEIR_FLAGS: dict[FlagKind, str] = {
    FlagKind.DEBT: "You still owe {name} for {description}.",
    FlagKind.GRUDGE: "{name} holds a grudge against you over {description}.",
    FlagKind.PROMISE: "You promised {name}: {description}.",
    FlagKind.BROKEN_PROMISE: "{name} knows you broke a promise: {description}.",
    FlagKind.SAVED_LIFE: "You once saved {name}'s life: {description}.",
    FlagKind.SECRET: "You told {name} a secret: {description}.",
}

VALUE_NAMES = ", ".join(value.value.replace("_", " ") for value in CoreValue)
VALUES = {value.value for value in CoreValue}

TAG = re.compile(
    r"\[\s*values?\s*:([^\]\n]*)\]?|^\s*values?\s*:(.*)$", re.IGNORECASE | re.MULTILINE
)
CUT_OFF = re.compile(r"\[[^\]\n]*$")
STAGE_DIRECTION = re.compile(r"\*[^*]*\*")
QUOTES = {'"': '"', "“": "”", "'": "'"}


@dataclass(frozen=True)
class Draft:
    """A line as written: its spoken text and the core values it touches."""

    text: str
    values: tuple[CoreValue, ...] = ()


def first_name(npc: Npc) -> str:
    return npc.name.split()[0]


def system_prompt(npc: Npc, config: ConversationConfig = DEFAULT_CONFIG) -> str:
    """Who the speaker is and how to answer. The same for every line they say."""
    ranked = sorted(npc.values.items(), key=lambda item: -item[1])
    most = ", ".join(_value_name(value) for value, _ in ranked[:5])
    least = ", ".join(_value_name(value) for value, _ in reversed(ranked[-3:]))
    return "\n\n".join(
        [
            f"You are {npc.name}, aged {npc.age}. Occupation: {npc.occupation}. You live in a "
            "small, modern village. Stay in character.",
            npc.persona,
            npc.backstory,
            f"How you speak: {npc.speaking_style}",
            f"What you care about most: {most}. What you care about least: {least}.\n"
            f"Your interests: {', '.join(npc.interests)}.",
            "You're in a face-to-face conversation. Reply with only your next spoken line: at "
            f"most {config.max_words} words, usually one or two sentences. Plain speech: no "
            "stage directions, quotation marks or name label. React to what was just said and "
            "don't repeat yourself.",
            "After the line, on a last line of its own, list the one to three core values the "
            "conversation is touching now, like this: [values: honesty, ambition]\n"
            f"Choose from: {VALUE_NAMES}.",
        ]
    )


def background(
    speaker: Npc,
    other: Npc,
    rel: Relationship,
    history: SharedHistory,
    memories: Sequence[Memory],
    topics: Sequence[Memory],
    place: str | None,
    now: datetime,
) -> str:
    """What the speaker knows going in: the other person, their history, what's on their mind."""
    name = first_name(other)
    where = f"at {place}" if place else "out in the street"
    parts = [
        f"It's {now:%H:%M}, {where}. You're with {name} ({other.name}, aged {other.age}, "
        f"{other.occupation}).",
        describe(rel, name),
    ]
    events = [
        f"- {_ago(event.timestamp, now)}, {'you' if event.actor == speaker.id else name}: "
        f"{event.action}"
        for event in history.events
    ]
    flags = [
        THEIR_FLAGS[flag.kind].format(name=name, description=flag.description.strip().rstrip("."))
        for flag in history.flags
        if flag.owner == other.id and flag.about == speaker.id
    ]
    if events:
        parts.append("Between you two:\n" + "\n".join(events))
    parts += flags
    if memories:
        parts.append("On your mind:\n" + "\n".join(f"- {m.content}" for m in memories))
    if topics:
        parts.append("News you might bring up:\n" + "\n".join(f"- {m.content}" for m in topics))
    return "\n\n".join(parts)


def turn_prompt(
    background: str,
    lines: Sequence[Line],
    names: Mapping[Id, str],
    cue: Cue,
    other: str,
    config: ConversationConfig = DEFAULT_CONFIG,
) -> str:
    recent = lines[-config.transcript_lines :]
    if recent:
        transcript = "\n".join(f"{names[line.speaker]}: {line.text}" for line in recent)
        if len(lines) > len(recent):
            transcript = f"...\n{transcript}"
        so_far = f"The conversation so far:\n{transcript}"
    else:
        so_far = "The conversation hasn't started yet."
    return "\n\n".join([background, so_far, CUES[cue].format(other=other)])


def parse_reply(text: str, names: Sequence[str] = (), others: Sequence[str] = ()) -> Draft:
    """The speaker's line and its values from a reply, without the tag, labels, stage directions
    or any turn written for `others`."""
    values: tuple[CoreValue, ...] = ()
    for match in TAG.finditer(text):
        values = _values(match.group(1) or match.group(2) or "")
    spoken = CUT_OFF.sub("", TAG.sub(" ", text).rstrip())
    for name in others:
        turn = re.search(rf"^\s*{re.escape(name)}\s*:", spoken, re.IGNORECASE | re.MULTILINE)
        if turn:
            spoken = spoken[: turn.start()]
    spoken = " ".join(STAGE_DIRECTION.sub(" ", spoken).split())
    for name in sorted(names, key=len, reverse=True):
        if spoken.lower().startswith(f"{name.lower()}:"):
            spoken = spoken[len(name) + 1 :].strip()
            break
    if len(spoken) >= 2 and QUOTES.get(spoken[0]) == spoken[-1]:
        spoken = spoken[1:-1].strip()
    return Draft(spoken, values)


def duration(text: str, config: ConversationConfig = DEFAULT_CONFIG) -> float:
    """Seconds to say `text` aloud at the configured pace."""
    return max(config.min_line_seconds, len(text.split()) * 60 / config.words_per_minute)


def _values(listed: str) -> tuple[CoreValue, ...]:
    found: list[CoreValue] = []
    for name in listed.split(","):
        key = re.sub(r"[\s-]+", "_", name.strip().strip(".").lower())
        if key in VALUES and CoreValue(key) not in found:
            found.append(CoreValue(key))
    return tuple(found)


def _value_name(value: CoreValue) -> str:
    return value.value.replace("_", " ")


def _ago(then: datetime, now: datetime) -> str:
    elapsed = now - then
    if elapsed < timedelta(hours=1):
        return "just now"
    if elapsed < timedelta(days=1):
        hours = int(elapsed / timedelta(hours=1))
        return f"{hours} hour{'s' if hours > 1 else ''} ago"
    days = elapsed.days
    return "yesterday" if days == 1 else f"{days} days ago"
