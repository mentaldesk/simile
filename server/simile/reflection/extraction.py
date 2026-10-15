from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, Field

from simile.npc.values import format_scores, ranked
from simile.reflection.config import DEFAULT_CONFIG, ReflectionConfig
from simile.schema import (
    PLAYER_ID,
    Aspect,
    Conversation,
    Flag,
    FlagKind,
    Id,
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


class NewFlag(BaseModel):
    kind: FlagKind = Field(
        description="From this person's side: debt, `about` owes them; grudge, they resent "
        "`about`; promise, `about` promised them something; broken_promise, `about` broke a "
        "promise to them; saved_life, `about` saved their life; secret, `about` told them a "
        "secret."
    )
    about: str = Field(description="The id of the other person.")
    description: str = Field(
        description="What it concerns, in a few words, e.g. 'fixing Ana's fence by Friday'."
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
    flags_opened: list[NewFlag] = Field(
        default=[],
        description="Lasting facts this person now holds about someone else because of this "
        "conversation: a promise made to them, a favour they're owed, a grudge, a secret they "
        "were told. Don't repeat a flag that's already open.",
    )
    flags_resolved: list[str] = Field(
        default=[],
        description="Refs (like F1) of this person's open flags that the conversation settled: "
        "a promise kept, a debt repaid, a grudge let go. A promise that was broken is resolved "
        "and opened again as a broken_promise.",
    )


class Extraction(BaseModel):
    reflections: list[Reflection] = Field(
        description="One for each person you're asked to reflect for."
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
) -> Context:
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
    return Context(conversation, reflecting, names, feelings, flags)


def prompt(context: Context, config: ReflectionConfig = DEFAULT_CONFIG) -> str:
    conversation = context.conversation
    people = [_person(context, npc, config) for npc in context.npcs.values()]
    parts = [
        "Reflect for each of these people. Feelings going in are scored from 0 to 1, where 0.5 "
        "is neutral and a familiarity of 0 means strangers.",
        *people,
    ]
    outsiders = [p for p in conversation.participants if p not in context.npcs]
    if outsiders:
        listed = "\n".join(f"- {p} ({context.names[p]})" for p in outsiders)
        parts.append(
            "Also in the conversation, with no reflection of their own, though what they did "
            f"still counts:\n{listed}"
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
    flags = [
        f"- {ref} ({flag.kind.value} about {flag.about}): {flag.description}"
        for ref, flag in context.flags.items()
        if flag.owner == npc.id
    ]
    if flags:
        lines.append("Open flags:\n" + "\n".join(flags))
    return "\n".join(lines)


def _outsider(participant: Id, config: ReflectionConfig) -> str:
    return config.player_name if participant == PLAYER_ID else participant
