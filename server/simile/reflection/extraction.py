from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from simile.behaviour import Options
from simile.behaviour.intentions import when
from simile.conversation.temptation import Lie
from simile.npc.values import format_scores, ranked
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.schema import (
    PLAYER_ID,
    Aspect,
    Conversation,
    Flag,
    FlagKind,
    Id,
    Intention,
    Medium,
    Npc,
    Relationship,
    Signed,
    Unit,
)
from simile.social import as_of, meet


class Deed(BaseModel):
    by: str = Field(description="The id of who did it: someone else in the conversation.")
    action: str = Field(
        description="What they did, as a short phrase without a subject that reads after their "
        "name, naming people rather than saying 'me' or 'you', e.g. 'promised to fix Ana's "
        "fence' or 'mocked Ben's paintings'."
    )
    aspects: list[Aspect] = Field(
        description="Which of this person's feelings about them it moves: like (do I enjoy "
        "them), trust (will they keep promises and secrets and not betray me), respect (do I "
        "rate their competence, standing or strength)."
    )
    valence: Signed = Field(
        description="How it landed with this person, from -1 (deeply hurtful) to 1 (wonderful)."
    )
    magnitude: Unit = Field(
        description="How much it mattered to this person, from 0 (barely) to 1 (enormously)."
    )


WHAT = {
    FlagKind.DEBT: "{who} owes {whom}",
    FlagKind.GRUDGE: "{who} holds a grudge against {whom}",
    FlagKind.PROMISE: "{who} promised {whom}",
    FlagKind.BROKEN_PROMISE: "{who} broke a promise to {whom}",
    FlagKind.SAVED_LIFE: "{who} saved the life of {whom}",
    FlagKind.SECRET: "{who} told {whom} a secret",
}
"""Each kind of flag as who did what to whom."""

HELD_BY_WHO = frozenset({FlagKind.GRUDGE})
"""The kinds whose flag `who` holds. `whom` holds the rest: who is owed, promised, let down, saved
or told."""


def owner_and_about(kind: FlagKind, who: Id, whom: Id) -> tuple[Id, Id]:
    """The flag's owner and who it's about, since F2's kinds read from the owner's side."""
    return (who, whom) if kind in HELD_BY_WHO else (whom, who)


def who_did_what(flag: Flag) -> str:
    held_by_who = flag.kind in HELD_BY_WHO
    who, whom = (flag.owner, flag.about) if held_by_who else (flag.about, flag.owner)
    return WHAT[flag.kind].format(who=who, whom=whom)


class NewFlag(BaseModel):
    kind: FlagKind = Field(
        description="What `who` did to `whom`: "
        + "; ".join(
            f"{kind}, {what.format(who='`who`', whom='`whom`')}" for kind, what in WHAT.items()
        )
        + "."
    )
    who: str = Field(
        description="The id of who owes, holds the grudge, made the promise, broke it, saved the "
        "life or told the secret."
    )
    whom: str = Field(
        description="The id of who they owe, hold the grudge against, promised, let down, saved "
        "or told."
    )
    description: str = Field(
        description="What it concerns, in a few words, e.g. 'fixing Ana's fence by Friday'."
    )


class Lending(BaseModel):
    lender: str = Field(description="The id of who lent the money.")
    borrower: str = Field(description="The id of who borrowed it.")
    amount: float = Field(description="How much, as a number.")


class Intent(BaseModel):
    who: str = Field(description="The id of the resident who said they'd do it.")
    kind: str = Field(
        description="Which of the things they can do it is: create (make something in their "
        "craft, including going to a wall or place to make it), go (go to a place), seek (look "
        "someone up for a chat) or news (read the news at a terminal)."
    )
    target: str | None = Field(
        default=None,
        description="For go, the place's id. For seek, the id of whom they'll look up. For create, "
        "the id of where they'll make it, or null. For news, the terminal's id, or null.",
    )
    description: str = Field(
        description="What they said they'd do, in a few words. For create, the idea itself as "
        "they described it, e.g. 'a mural of an ocean of coffee with cups half-sunk in it'."
    )
    promised_to: list[str] = Field(default=[], description="The ids of whoever they said it to.")
    when: str = Field(
        description="'now' if they'll do it straight after the conversation, or else when they "
        "said, as 'today HH:MM' or 'tomorrow HH:MM'."
    )


class Reflection(BaseModel):
    npc: str = Field(description="The id of the person this reflection is for.")
    summary: str = Field(
        description="What they'll remember of the conversation, in their own words in the first "
        "person, in one or two sentences that name who they talked with."
    )
    valence: Signed = Field(description="How they felt about the conversation, from -1 to 1.")
    salience: Unit = Field(
        description="How much it mattered to them, from 0 (forgettable small talk) to 1 "
        "(they'll never forget it)."
    )
    topics: list[str] = Field(
        default=[], description="One to three short lowercase topics it was about."
    )
    events: list[Deed] = Field(
        default=[],
        description="What the others did in the conversation that changed how this person "
        "feels about them, judged by what this person cares about. Pleasant talk about things "
        "they care about is a small positive event for like. Leave out what didn't matter.",
    )


class Extraction(BaseModel):
    reflections: list[Reflection] = Field(
        description="One for each person you're asked to reflect for."
    )
    flags_opened: list[NewFlag] = Field(
        default=[],
        description="Lasting facts between two people in the conversation that it created, each "
        "as who did what to whom: a promise made, a debt run up, a grudge formed, a life saved, "
        "a secret told. Don't repeat a flag that's already open.",
    )
    flags_resolved: list[str] = Field(
        default=[],
        description="Refs (like F1) of open flags that the conversation settled: a promise "
        "kept, a debt repaid, a grudge let go. A promise that was broken is resolved and opened "
        "again as a broken_promise.",
    )
    loans: list[Lending] = Field(
        default=[],
        description="Money one person in the conversation agreed to lend the other, there and "
        "then. Leave out a loan that was only talked about or turned down. A loan is kept as a "
        "debt, so don't open a debt flag for it as well.",
    )
    intentions: list[Intent] = Field(
        default=[],
        description="What each resident said they'd do, within a day, as one of the things "
        "they can do: 'I'll go and paint it now' is create, now. Leave out plans that are vague "
        "('one day', 'some time'), only maybe, already planned or for after tomorrow, anything "
        "they can't do here, and what the visitor said they'd do.",
    )
    lies: list[str] = Field(
        default=[],
        description="Refs (like L1) of the lies listed that were told in the conversation, in "
        "those words or others. Leave out any that never came up.",
    )


SYSTEM = (
    "You read conversations between people in a small, modern village and work out what each "
    "one meant to the people in it. Judge it from each person's own side, by what they care "
    "about: the same remark can please one person and offend another. Be honest about rudeness, "
    "kindness, promises and secrets, but don't read drama into small talk. Refer to people by "
    "their ids."
)


class Relationships(Protocol):
    def relationship(self, owner: str, about: str) -> Relationship | None: ...


@dataclass(frozen=True)
class Context:
    """What the reflection prompt is built from, read before the LLM call."""

    conversation: Conversation
    npcs: dict[Id, Npc]
    """The participants who reflect: everyone with an NPC record."""
    names: dict[Id, str]
    """What each participant is called in the transcript."""
    feelings: dict[tuple[Id, Id], Relationship]
    """How each NPC felt about each other participant going in."""
    flags: dict[str, Flag]
    """Their open flags about each other, by the ref the prompt gives them."""
    options: dict[Id, Options] = field(default_factory=dict)
    """What each NPC could say they'll do."""
    planned: dict[Id, list[Intention]] = field(default_factory=dict)
    """What each NPC has already said they'd do."""
    residents: dict[Id, Npc] = field(default_factory=dict)
    """Everyone in the village, whom a resident could say they'll look up."""
    lies: dict[str, Lie] = field(default_factory=dict)
    """The lies its residents were set up to tell, by the ref the prompt gives them."""

    @property
    def now(self) -> datetime:
        return ended_at(self.conversation)

    def others(self, npc: Id) -> list[Id]:
        return [other for other in self.conversation.participants if other != npc]

    def who(self, text: str) -> Id | None:
        """The participant `text` names, by id, transcript name or full name."""
        key = text.strip().lower()
        for participant in self.conversation.participants:
            npc = self.npcs.get(participant)
            names = (participant, self.names[participant], npc.name if npc else participant)
            if key in (name.lower() for name in names):
                return participant
        return None


def ended_at(conversation: Conversation) -> datetime:
    if conversation.ended is not None:
        return conversation.ended
    return conversation.lines[-1].timestamp if conversation.lines else conversation.started


def relationship(store: Relationships, npc: Npc, about: Id, now: datetime) -> Relationship:
    """How `npc` feels about `about` at `now`, decayed since they last met."""
    stored = store.relationship(npc.id, about)
    return as_of(stored, now) if stored else meet(npc, about)


def gather(
    conversation: Conversation,
    npcs: Mapping[Id, Npc],
    store: Relationships,
    config: ReflectionConfig = DEFAULT_CONFIG,
    *,
    options: Mapping[Id, Options] | None = None,
    planned: Mapping[Id, Sequence[Intention]] | None = None,
    lies: Sequence[Lie] = (),
) -> Context:
    """With `options`, what each NPC could say they'll do, `planned`, what they have, and
    `lies`, what they were set up to lie about."""
    now = ended_at(conversation)
    reflecting = {p: npcs[p] for p in conversation.participants if p in npcs}
    names = {
        p: npcs[p].name.split()[0] if p in npcs else _outsider(p, config)
        for p in conversation.participants
    }
    feelings = {
        (npc, other): relationship(store, reflecting[npc], other, now)
        for npc in reflecting
        for other in conversation.participants
        if other != npc
    }
    open_flags = [flag for rel in feelings.values() for flag in rel.flags if flag.resolved is None]
    flags = {f"F{n}": flag for n, flag in enumerate(open_flags, start=1)}
    options, planned = options or {}, planned or {}
    return Context(
        conversation,
        reflecting,
        names,
        feelings,
        flags,
        {npc: options[npc] for npc in reflecting if npc in options},
        {npc: list(planned[npc]) for npc in reflecting if planned.get(npc)},
        dict(npcs),
        {f"L{n}": lie for n, lie in enumerate(_present(lies, conversation), start=1)},
    )


def _present(lies: Sequence[Lie], conversation: Conversation) -> list[Lie]:
    there = set(conversation.participants)
    return [lie for lie in lies if {lie.liar, lie.listener} <= there]


def prompt(context: Context, config: ReflectionConfig = DEFAULT_CONFIG) -> str:
    conversation = context.conversation
    people = [_person(context, npc, config) for npc in context.npcs.values()]
    parts = [
        f"It's {context.now:%A %H:%M}. Reflect for each of these people. Feelings going in are "
        "scored from 0 to 1, where 0.5 is neutral and a familiarity of 0 means strangers.",
        *people,
    ]
    if context.options:
        others = [npc for npc in context.residents if npc not in conversation.participants]
        listed = ", ".join(f"{npc} ({context.residents[npc].name})" for npc in others)
        parts.append(f"Others in the village they could look up: {listed or 'nobody'}.")
    outsiders = [p for p in conversation.participants if p not in context.npcs]
    if outsiders:
        listed = "\n".join(f"- {p} ({context.names[p]})" for p in outsiders)
        parts.append(
            "Also in the conversation, with no reflection of their own, though what they did "
            f"still counts:\n{listed}"
        )
    if context.flags:
        listed = "\n".join(
            f"- {ref} ({flag.kind.value}): {who_did_what(flag)}: {flag.description}"
            for ref, flag in context.flags.items()
        )
        parts.append(f"Open flags between them:\n{listed}")
    if context.lies:
        listed = "\n".join(
            f"- {ref}: {lie.said} {context.names[lie.listener]} "
            + ("knows it isn't true." if lie.known else "didn't know, and believed it.")
            for ref, lie in context.lies.items()
        )
        parts.append(
            "Lies they were set up to tell if it came up. List the refs of those told under "
            f"lies:\n{listed}"
        )
    lines = conversation.lines[-config.transcript_lines :]
    transcript = "\n".join(f"{context.names[line.speaker]}: {line.text}" for line in lines)
    if len(conversation.lines) > len(lines):
        transcript = f"...\n{transcript}"
    parts.append(f"The conversation:\n{transcript}")
    return "\n\n".join(parts)


def _person(context: Context, npc: Npc, config: ReflectionConfig) -> str:
    order = ranked(npc.values)
    most = format_scores(order[: config.cares_most])
    least = format_scores(order[::-1][: config.cares_least])
    lines = [
        f"{npc.id} ({npc.name}, {npc.age}, {npc.occupation}). {npc.persona}",
        f"Cares most about: {most}. Cares least about: {least}.",
        f"Interests: {', '.join(npc.interests)}.",
    ]
    for other in context.others(npc.id):
        rel = context.feelings[(npc.id, other)]
        lines.append(
            f"Going in, about {context.names[other]}: like {rel.like:.2f}, trust {rel.trust:.2f}, "
            f"respect {rel.respect:.2f}, familiarity {rel.familiarity:.2f}."
        )
    if npc.id in context.options:
        lines.append(f"Can do: {can_do(context.options[npc.id])}.")
    if planned := context.planned.get(npc.id):
        listed = "; ".join(
            f"{i.kind.value}{f' {i.target}' if i.target else ''} ({when(i.due, context.now)}): "
            f"{i.description}"
            for i in planned
        )
        lines.append(f"Already planned: {listed}.")
    return "\n".join(lines)


CRAFTS = {
    Medium.WRITING: "write",
    Medium.PAINTING: "paint a canvas for the gallery",
    Medium.MURAL: "paint",
}


def can_do(options: Options) -> str:
    """The ids of what an NPC could say they'll do, for the prompt."""
    places = ", ".join(f"{id} ({name})" for id, name in options.places.items())
    parts = [
        f"go to {places}",
        f"news at {', '.join(options.terminals)}",
        "seek anyone here or in the village, or the visitor (player)",
    ]
    if options.medium is not None:
        where = ", ".join(f"{id} ({name})" for id, name in options.making.items())
        craft = CRAFTS[options.medium]
        parts.append(f"create ({craft}) at {where}" if where else f"create ({craft}), not now")
    return "; ".join(parts)


def _outsider(participant: Id, config: ReflectionConfig) -> str:
    return config.player_name if participant == PLAYER_ID else participant
