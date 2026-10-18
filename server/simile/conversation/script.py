import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.needs import feels
from simile.conversation.plan import Plan, direction
from simile.conversation.prompt import (
    BOUNDS,
    VALUE_NAMES,
    Draft,
    WorkTopic,
    ago,
    detailed,
    first_name,
    habits,
    parse_reply,
    rough_edges,
    stuck,
    value_name,
)
from simile.memory import SharedHistory
from simile.schema import FlagKind, Id, Memory, Npc, Relationship
from simile.social import describe

BETWEEN: dict[FlagKind, str] = {
    FlagKind.DEBT: "{about} still owes {owner} for {description}.",
    FlagKind.PROMISE: "{about} promised {owner}: {description}.",
    FlagKind.BROKEN_PROMISE: "{about} broke a promise to {owner}: {description}.",
    FlagKind.SAVED_LIFE: "{about} once saved {owner}'s life: {description}.",
    FlagKind.SECRET: "{about} told {owner} a secret: {description}. Only the two of them know it.",
}

VERBS = {
    "like": "likes",
    "dislike": "dislikes",
    "trust": "trusts",
    "respect": "respects",
    "have": "has",
    "know": "knows",
    "hold": "holds",
    "don't": "doesn't",
    "can't": "can't",
}
CLAUSE_VERB = re.compile(rf"(^You |, | and | but )(barely )?({'|'.join(VERBS)})\b")
SENTENCE = re.compile(r"(?<=[.!?])\s+")
LABEL = r"^[\s*_]*(?P<name>{names})[\s*_]*(?:\([^)\n]*\))?[\s*_]*:(?:\*\*|__)?\s*(?P<text>.*)$"


@dataclass(frozen=True)
class Character:
    """What one side of a scripted conversation brings to it."""

    npc: Npc
    feelings: Relationship
    """How they feel about the other."""
    memories: Sequence[Memory] = ()
    topics: Sequence[Memory] = ()
    """News they might bring up."""
    secrets: Sequence[tuple[str, str]] = ()
    """Who told them what in confidence, among people other than the other."""
    works: Sequence[WorkTopic] = ()
    plans: str = ""
    """What they could plan to do in the village, and what they've already said they'll do."""


@dataclass(frozen=True)
class ScriptLine:
    speaker: Id
    draft: Draft


def script_system(config: ConversationConfig = DEFAULT_CONFIG) -> str:
    """How to write a scene. The same for every conversation."""
    bounds = BOUNDS.format(own="the speaker's own", they="they")
    return "\n\n".join(
        [
            "You write the dialogue for a life simulation set in a small, modern village. Each "
            "scene is one conversation between two residents, written like a scene in a novel: "
            "two distinct people, each with their own voice, mood and reasons, talking the way "
            "neighbours really do.",
            "- Each character knows only what their own notes say, what's between them, and "
            "what's been said earlier in the scene. Neither mentions what only the other knows, "
            "and what someone was told in confidence stays with them. The notes are in their own "
            "words: they draw on them but never recite them.\n"
            "- Each knows what someone with their life and job would know. Outside that, they "
            "ask, admit they don't know, or give a personal angle rather than expert advice.\n"
            "- It's a chat between neighbours, not a consultation: they listen, react and share "
            "more than they advise.\n"
            "- Let the talk move on. When one brings up something the other doesn't take up, "
            "they let it go. Nobody goes back over a point that's been made, and nobody repeats "
            "themselves.\n"
            "- Follow the direction: who's keen, who wants to leave and when, and the length. The "
            "scene ends when they part, with a goodbye and its answer.\n"
            "- Nobody promises to do what isn't in their notes' list of what they could plan to "
            "do. Someone who has said they'll go and do something now says where they're off to "
            "as they leave.\n"
            "- Use each character's pet words, phrases and verbal habits now and then, not in "
            "every line, and vary how their lines begin.\n"
            "- Nobody agrees just to be pleasant. Saying no, being brief, or disagreeing is fine "
            "when it's in character.\n"
            f"- {bounds}",
            "Write only the spoken lines, one a line, each starting with the speaker's first "
            "name and a colon and ending with the one to three core values the line touches, "
            "like this:\nMara: Morning! Lovely out, isn't it? [values: connection]\n"
            f"Choose from: {VALUE_NAMES}.\n"
            f"Each line is at most {config.max_words} words, often far fewer. No narration, "
            "stage directions, headings or quotation marks.",
        ]
    )


def scene_prompt(
    a: Character,
    b: Character,
    history: SharedHistory,
    place: str | None,
    now: datetime,
    plan: Plan,
) -> str:
    """Both sides of the conversation `a` starts with `b`, what's between them and the direction,
    with what stuck with one of them from one article they read, `a`'s if they can."""
    names = {a.npc.id: first_name(a.npc), b.npc.id: first_name(b.npc)}
    where = f"at {place}" if place else "out in the street"
    detail = detailed(a.topics, b.topics)
    parts = [
        f"It's {now:%H:%M}, {where}. {names[a.npc.id]} has just walked up to {names[b.npc.id]}.",
        character(a, b.npc, grudges(history, a.npc.id), plan.stances[a.npc.id].mood, detail),
        character(b, a.npc, grudges(history, b.npc.id), plan.stances[b.npc.id].mood, detail),
    ]
    between = [
        f"- {ago(event.timestamp, now)}, {names.get(event.actor, event.actor)}: {event.action}"
        for event in history.events
    ]
    between += [
        "- "
        + BETWEEN[flag.kind].format(
            owner=names[flag.owner],
            about=names[flag.about],
            description=flag.description.strip().rstrip("."),
        )
        for flag in history.flags
        if flag.resolved is None
        and flag.kind in BETWEEN
        and flag.owner in names
        and flag.about in names
    ]
    if between:
        parts.append("## Between them\n" + "\n".join(between))
    parts.append("## Direction\n" + direction(plan))
    return "\n\n".join(parts)


def grudges(history: SharedHistory, owner: Id) -> list[str]:
    return [
        flag.description.strip().rstrip(".")
        for flag in history.flags
        if flag.kind is FlagKind.GRUDGE and flag.owner == owner and flag.resolved is None
    ]


def character(
    side: Character,
    them: Npc,
    grudges: Sequence[str] = (),
    mood: Sequence[str] = (),
    detail: Memory | None = None,
) -> str:
    npc, name, other = side.npc, first_name(side.npc), first_name(them)
    ranked = sorted(npc.values.items(), key=lambda item: -item[1])
    most = ", ".join(value_name(value) for value, _ in ranked[:5])
    least = ", ".join(value_name(value) for value, _ in reversed(ranked[-3:]))
    feelings = third_person(describe(side.feelings.model_copy(update={"flags": []}), other), name)
    speech = f"How {name} speaks: {npc.speaking_style}"
    if npc.mannerisms:
        speech += (
            f"\n{name}'s verbal habits: {habits(npc)}. Use these now and then, not in every line."
        )
    parts = [
        f"## {name}\n{npc.name}, aged {npc.age}. Occupation: {npc.occupation}.",
        npc.persona,
        npc.backstory,
        speech,
        f"Cares most about: {most}. Cares least about: {least}.\n"
        f"Interests: {', '.join(npc.interests)}.",
    ]
    if edges := rough_edges(npc, name):
        parts.append(" ".join(edges))
    parts.append(feelings)
    if mood:
        parts.append(feels(name, mood))
    parts += [
        f"{name} holds a grudge against {other} over {grudge}, which only {name} knows."
        for grudge in grudges
    ]
    if side.plans:
        parts.append(side.plans)
    if side.memories:
        parts.append(
            f"On {name}'s mind, which only {name} knows:\n"
            + "\n".join(f"- {m.content}" for m in side.memories)
        )
    if side.secrets:
        parts.append(
            f"Told to {name} in confidence, which only {name} knows:\n"
            + "\n".join(f"- {who}: {what.strip()}" for who, what in side.secrets)
        )
    own = [topic for topic in side.works if topic.work.artist == npc.id]
    by_others = [topic for topic in side.works if topic.work.artist != npc.id]
    if own:
        parts.append(
            f"{name}'s own works, which {name} might bring up and stand by, in notes only {name} "
            "knows:\n" + "\n".join(work_line(topic, them) for topic in own)
        )
    if by_others:
        parts.append(
            f"Works by others {name} might bring up, which only {name} knows:\n"
            + "\n".join(work_line(topic, them) for topic in by_others)
        )
    if side.topics:
        parts.append(
            f"News {name} read and might bring up:\n"
            + "\n".join(f"- {m.content}" for m in side.topics)
        )
    if detail is not None and detail in side.topics:
        parts.append(stuck(detail, name))
    return "\n\n".join(parts)


def work_line(topic: WorkTopic, them: Npc) -> str:
    made = f" ({first_name(them)} made it.)" if topic.work.artist == them.id else ""
    return f"- {topic.memory.content}{made}"


def continue_prompt(scene: str, written: Sequence[ScriptLine], names: Mapping[Id, str]) -> str:
    so_far = "\n".join(f"{names[line.speaker]}: {line.draft.text}" for line in written)
    return (
        f"{scene}\n\n## The scene so far\n{so_far}\n\n"
        "Write the rest of the scene, from the next line to the goodbyes, in the same format. "
        "If it has already ended, write nothing."
    )


def third_person(text: str, name: str) -> str:
    """R1's second-person `describe()` about `name`'s feelings, told about `name`."""
    sentences = []
    for sentence in SENTENCE.split(text):
        if sentence.startswith("You "):
            sentence = CLAUSE_VERB.sub(lambda m: f"{m[1]}{m[2] or ''}{VERBS[m[3]]}", sentence)
            sentence = name + sentence.removeprefix("You")
        sentence = re.sub(r"\byour\b", f"{name}'s", sentence, flags=re.IGNORECASE)
        sentences.append(re.sub(r"\byou\b", name, sentence, flags=re.IGNORECASE))
    return " ".join(sentences)


class ScriptParser:
    """A script's lines as they finish streaming, each cleaned like `parse_reply`. Lines that
    don't start with a speaker's name are left out."""

    def __init__(
        self, names: Mapping[Id, Sequence[str]], config: ConversationConfig = DEFAULT_CONFIG
    ) -> None:
        self.names = {npc: list(spelt) for npc, spelt in names.items()}
        self.config = config
        self._text = ""
        spellings = sorted(
            ((spelling, npc) for npc, spelt in names.items() for spelling in spelt),
            key=lambda item: -len(item[0]),
        )
        self._speakers = {spelling.lower(): npc for spelling, npc in spellings}
        alternatives = "|".join(re.escape(spelling) for spelling, _ in spellings)
        self._label = re.compile(LABEL.format(names=alternatives), re.IGNORECASE)

    def feed(self, chunk: str) -> list[ScriptLine]:
        self._text += chunk
        *complete, self._text = self._text.split("\n")
        return [line for text in complete if (line := self._line(text))]

    def end(self) -> list[ScriptLine]:
        """The last line, once the stream has finished."""
        return self.feed("\n")

    def _line(self, text: str) -> ScriptLine | None:
        labelled = self._label.match(text)
        if labelled is None:
            return None
        speaker = self._speakers[labelled["name"].lower()]
        others = [name for npc, spelt in self.names.items() if npc != speaker for name in spelt]
        draft = parse_reply(labelled["text"], self.names[speaker], others, self.config)
        return ScriptLine(speaker, draft) if draft.text else None
