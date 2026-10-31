import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from simile.conversation.temptation import CUES, Kind, Temptation
from simile.schema import Disappearance, Fact, Id, Knower, Memory
from simile.story.disappearance import question

SUBJECT = "what happened to Aris"
TELL = 'You remember this, and trust {other} enough to tell them if they ask: "{remembers}"'
KEEP = (
    "You know more about Aris going missing than you let on, but you don't trust "
    "{other} enough to say what. If it comes up, say you'd rather not talk about it, without "
    "denying that you know something."
)
HIDES = "{Who} won't say {question}."
COVER = 'Only if asked that, {say} exactly: "{cover}"'
UNASKED = (
    "Give each of those cover stories only when asked that very question. Never bring one up "
    "yourself, and add no other denial about Aris or her going missing."
)


class Stance(StrEnum):
    """How a resident answers about a fact they know: tell it, lie, or keep it back."""

    TELL = "tell"
    LIE = "lie"
    KEEP = "keep"


def stance(knower: Knower, trust: float) -> Stance:
    """Tell it from `tells_from` trust, and below it lie with a cover or else keep quiet."""
    if knower.tells_from is not None and trust >= knower.tells_from:
        return Stance.TELL
    return Stance.LIE if knower.cover is not None else Stance.KEEP


@dataclass(frozen=True)
class Telling:
    """What a resident is set up to say about one of the story's facts."""

    fact: Fact
    knower: Knower
    stance: Stance
    remembers: str
    """Their memory of it, or what happened if they have none."""

    def temptation(self) -> Temptation:
        """The cover story as one of #285's lies, tied to its question, without the truth."""
        asked = question(self.fact.id, self.knower.how)
        return Temptation(
            Kind.FACT,
            self.knower.id,
            f"fact/{self.fact.id}",
            HIDES.replace("{question}", asked),
            COVER.replace("{cover}", self.knower.cover or ""),
            SUBJECT,
            involves=frozenset(self.fact.about),
            known_by=frozenset(k.id for k in self.fact.known_by if k.id != self.knower.id),
            fact_id=self.fact.id,
        )


def told(tellings: Iterable[Telling], other: str) -> list[str]:
    """The directions for what they'll tell `other`, and for what they keep back, once."""
    tellings = list(tellings)
    directions = [
        TELL.format(other=other, remembers=t.remembers) for t in tellings if t.stance is Stance.TELL
    ]
    if any(t.stance is Stance.KEEP for t in tellings):
        directions.append(KEEP.format(other=other))
    return directions


def asked(said: str) -> bool:
    """Whether `said` touches on Aris."""
    return re.search(rf"\b(?:{CUES[Kind.FACT]})\b", said, re.IGNORECASE) is not None


def tellings(
    disappearance: Disappearance | None, npc: Id, trust: float, memories: Sequence[Memory] = ()
) -> list[Telling]:
    """What `npc` would say of each fact they know, in their first memory of it, at `trust`."""
    if disappearance is None:
        return []
    remembered: dict[Id, str] = {}
    for memory in sorted(memories, key=lambda memory: memory.timestamp):
        if memory.fact_id:
            remembered.setdefault(memory.fact_id, memory.content)
    return [
        Telling(fact, knower, stance(knower, trust), remembered.get(fact.id, fact.what))
        for fact in disappearance.facts
        for knower in fact.known_by
        if knower.id == npc
    ]
