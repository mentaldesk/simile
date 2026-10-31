from enum import StrEnum
from typing import Annotated, Self

from pydantic import Field, model_validator

from simile.schema.common import Id, Key, Model, Signed, Timestamp, Unit

Point = Annotated[str, Field(min_length=1, max_length=240)]


class Aspect(StrEnum):
    LIKE = "like"
    TRUST = "trust"
    RESPECT = "respect"


class InteractionEvent(Model):
    """Something `actor` did that changes how `target` feels about them."""

    actor: Id
    target: Id
    action: str = Field(description="What the actor did, in a few words.")
    aspects: list[Aspect] = Field(
        description="Which of the target's feelings about the actor it moves. "
        "Familiarity grows with any event."
    )
    valence: Signed = Field(description="How it landed with the target, from -1 to 1.")
    magnitude: Unit = Field(description="How much it mattered, 0-1.")
    timestamp: Timestamp
    conversation_id: Key | None = None

    @model_validator(mode="after")
    def _two_parties(self) -> Self:
        if self.actor == self.target:
            raise ValueError("actor and target must differ")
        return self


class FlagKind(StrEnum):
    """From the owner's side: `debt`, `about` owes the owner; `grudge`, the owner resents `about`;
    `promise`, `about` promised the owner something; `broken_promise`, `about` broke one;
    `saved_life`, `about` saved the owner's life; `secret`, `about` told the owner a secret."""

    DEBT = "debt"
    GRUDGE = "grudge"
    PROMISE = "promise"
    BROKEN_PROMISE = "broken_promise"
    SAVED_LIFE = "saved_life"
    SECRET = "secret"


class Flag(Model):
    """A discrete fact `owner` holds about `about` that persists after the scores recover."""

    id: Key
    kind: FlagKind
    owner: Id
    about: Id
    description: str = Field(description="What it concerns, in a few words, for prompts.")
    created: Timestamp
    resolved: Timestamp | None = Field(
        default=None, description="When it stopped applying, e.g. a debt repaid. Null while open."
    )


class Baseline(Model):
    """Where like, trust and respect drift back to without contact."""

    like: Unit
    trust: Unit
    respect: Unit


class Relationship(Model):
    """How `owner` feels about `about`. Each direction is a separate relationship."""

    owner: Id
    about: Id
    like: Unit
    trust: Unit
    respect: Unit
    familiarity: Unit
    baseline: Baseline
    flags: list[Flag] = []
    last_interaction: Timestamp | None = None

    @model_validator(mode="after")
    def _consistent(self) -> Self:
        if self.owner == self.about:
            raise ValueError("owner and about must differ")
        for flag in self.flags:
            if (flag.owner, flag.about) != (self.owner, self.about):
                raise ValueError(f"flag {flag.id} belongs to another relationship")
        return self


class MemoryKind(StrEnum):
    """`work` is making, reading or seeing a work. `past` is from their life before the game."""

    CONVERSATION = "conversation"
    NEWS = "news"
    OBSERVATION = "observation"
    WORK = "work"
    PAST = "past"


class Memory(Model):
    owner: Id
    kind: MemoryKind
    content: str = Field(description="The memory in the owner's own words, ready for a prompt.")
    points: list[Point] = Field(
        default=[],
        max_length=3,
        exclude_if=lambda points: not points,
        description='Up to 3 specific things the owner took from what they read, e.g. "the '
        'council votes on the drone rules in May". Kept out of `content` so a prompt can '
        "include them for one article at a time. Left out when empty.",
    )
    salience: Unit = Field(description="How much it matters to the owner, 0-1.")
    valence: Signed = Field(description="How the owner felt about it, from -1 to 1.")
    timestamp: Timestamp
    about: list[Id] = Field(default=[], description="Entities the memory involves.")
    topics: list[str] = []
    conversation_id: Key | None = None
    news_id: Key | None = None
    work_id: Key | None = None
    fact_id: Id | None = Field(
        default=None,
        exclude_if=lambda fact_id: fact_id is None,
        description="The story's `Fact` it holds, for a memory seeded from one. A memory "
        "passed on from it keeps it. Left out when there isn't one.",
    )
