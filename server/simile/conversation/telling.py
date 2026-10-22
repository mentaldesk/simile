import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from simile.conversation.temptation import CUES, Kind, Temptation
from simile.schema import Fact, Id, Incident, Knower, Memory

SUBJECT = "what happened to Aris"
TELL = 'You remember this, and trust {other} enough to tell them if they ask: "{remembers}"'
KEEP = (
    "You know more about the night Aris was attacked than you let on, but you don't trust "
    "{other} enough to say what. If it comes up, say you'd rather not talk about it, without "
    "denying that you know something."
)
HIDES = '{Who} remember{s} this, but won\'t own up to it: "{remembers}"'
COVER = 'If it comes up, {say} "{cover}"'


class Stance(StrEnum):
    """How a resident answers about a fact they know: they tell it, lie with their cover story,
    or keep it back."""

    TELL = "tell"
    LIE = "lie"
    KEEP = "keep"


def stance(knower: Knower, trust: float) -> Stance:
    """Tell it from `tells_from` trust in whoever asks, and below it lie if there's a cover
    story, or else keep quiet."""
    if knower.tells_from is not None and trust >= knower.tells_from:
        return Stance.TELL
    return Stance.LIE if knower.cover is not None else Stance.KEEP


@dataclass(frozen=True)
class Telling:
    """What a resident is set up to say about one of the incident's facts."""

    fact: Fact
    knower: Knower
    stance: Stance
    remembers: str
    """Their memory of it, or what happened if they have none."""

    def direction(self, other: str) -> str:
        """Told to them, for a conversation with `other`."""
        if self.stance is Stance.TELL:
            return TELL.format(other=other, remembers=self.remembers)
        if self.stance is Stance.KEEP:
            return KEEP.format(other=other)
        return self.temptation().direction()

    def temptation(self) -> Temptation:
        """The cover story as one of #285's lies, for B3 and the eye."""
        return Temptation(
            Kind.FACT,
            self.knower.id,
            f"fact/{self.fact.id}",
            HIDES.replace("{remembers}", self.remembers),
            COVER.replace("{cover}", self.knower.cover or ""),
            SUBJECT,
            involves=frozenset(self.fact.about),
            known_by=frozenset(k.id for k in self.fact.known_by if k.id != self.knower.id),
            fact_id=self.fact.id,
        )


def asked(said: str) -> bool:
    """Whether `said` touches the incident."""
    return re.search(rf"\b(?:{CUES[Kind.FACT]})\b", said, re.IGNORECASE) is not None


def tellings(
    incident: Incident | None, npc: Id, trust: float, memories: Sequence[Memory] = ()
) -> list[Telling]:
    """What `npc` would say about each fact they know to someone they trust `trust`, in the
    words of their `memories` of it."""
    if incident is None:
        return []
    remembered = {memory.fact_id: memory.content for memory in memories if memory.fact_id}
    return [
        Telling(fact, knower, stance(knower, trust), remembered.get(fact.id, fact.what))
        for fact in incident.facts
        for knower in fact.known_by
        if knower.id == npc
    ]
