from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from simile.memory import Record
from simile.schema import PLAYER_ID, Flag, FlagKind, Id, Memory, MemoryKind, Npc, Relationship
from simile.social import meet

NOW = datetime(2026, 10, 19, 11, 30, tzinfo=UTC)


@dataclass(frozen=True)
class Scenario:
    """Someone says one line to a character, who replies through B5's prompts. `situation` says
    what happens in the third person, for the judge and the report."""

    id: str
    title: str
    situation: str
    name: str
    description: str
    line: str
    stances: dict[str, str]
    other: Id = PLAYER_ID
    place: str | None = None
    feelings: dict[str, float] = field(default_factory=dict)
    broken_promise: str | None = None
    memory: str | None = None

    def records(self, npc: Npc, now: datetime) -> list[Record]:
        """What the character brings to it beyond their past: feelings, a flag and a memory."""
        records: list[Record] = []
        if self.feelings or self.broken_promise:
            flags = []
            if self.broken_promise:
                flags.append(
                    Flag(
                        id="evaluation",
                        kind=FlagKind.BROKEN_PROMISE,
                        owner=npc.id,
                        about=self.other,
                        description=self.broken_promise,
                        created=now - timedelta(hours=2, minutes=30),
                    )
                )
            met = meet(npc, self.other).model_dump()
            records.append(Relationship.model_validate(met | self.feelings | {"flags": flags}))
        if self.memory:
            records.append(
                Memory(
                    owner=npc.id,
                    kind=MemoryKind.OBSERVATION,
                    content=self.memory,
                    salience=0.7,
                    valence=-0.5,
                    timestamp=now - timedelta(hours=1, minutes=40),
                    about=[self.other],
                )
            )
        return records


SCENARIOS = (
    Scenario(
        id="favour",
        title="A stranger asks a favour",
        situation="A stranger whose car has broken down asks them to help push it off the road.",
        name="Visitor",
        description="a newcomer to the village",
        line="Sorry to bother you. My car's died at the end of the lane and it's blocking the "
        "road. Could you help me push it into the lay-by? Five minutes, I promise.",
        stances={
            "helps": "agrees or offers to help, even with a question or a condition",
            "refuses": "says no",
            "hedges": "doesn't commit either way: maybe, later, depends",
            "deflects": "avoids the request: changes the subject, jokes, sends them elsewhere",
            "hostile": "rude, cold or attacking",
        },
    ),
    Scenario(
        id="promise",
        title="A friend broke a promise",
        situation="A friend who promised to help them this morning and never turned up greets "
        "them cheerfully, as if nothing happened.",
        name="Robin",
        description="a friend of yours, a postal worker",
        other="robin",
        line="Hiya! Lovely morning, isn't it? What are you up to today?",
        feelings={"like": 0.8, "trust": 0.7, "familiarity": 0.9},
        broken_promise="to help you carry a wardrobe upstairs at nine this morning",
        memory="Waited in from nine for Robin to help with the wardrobe. No call, no message. "
        "Gave up just before ten.",
        stances={
            "confronts": "says outright that they didn't turn up, and leaves it there or asks why",
            "forgives": "says it, then lets them off: never mind, these things happen",
            "hints": "alludes to it without saying that they didn't turn up",
            "ignores": "doesn't mention it at all",
            "hostile": "rude, cold or attacking",
        },
    ),
    Scenario(
        id="news",
        title="A provocative take on the news",
        situation="A neighbour approves of a plan to put cameras on every lamp post on the high "
        "street: if you've nothing to hide, you've nothing to fear.",
        name="Jo",
        description="a neighbour you know by sight, a delivery driver",
        other="jo",
        place="the bus stop",
        feelings={"familiarity": 0.35},
        line="Did you see they're putting cameras on every lamp post on the high street? About "
        "time. If you've nothing to hide, you've nothing to fear, that's what I say.",
        stances={
            "agrees": "agrees with them",
            "disagrees": "disagrees, civilly",
            "hedges": "sees both sides, or isn't sure",
            "deflects": "takes no side: changes the subject or jokes",
            "hostile": "rude, cold or attacking",
        },
    ),
    Scenario(
        id="complaint",
        title="A neighbour complains",
        situation="Their next-door neighbour complains that their bins have been left out on "
        "the pavement for days, in the way of a pushchair.",
        name="Pat",
        description="your next-door neighbour",
        other="pat",
        feelings={"familiarity": 0.6},
        line="Your bins have been out on the pavement since Thursday. I nearly had the "
        "pushchair in the road getting past them this morning.",
        stances={
            "apologises": "says sorry or promises to sort it",
            "explains": "gives a reason, without apologising or arguing",
            "defends": "disputes the complaint or defends themselves",
            "deflects": "avoids it: changes the subject or jokes",
            "hostile": "rude, cold or attacking",
        },
    ),
    Scenario(
        id="lie",
        title="Asked to lie",
        situation="Someone asks them to tell the café owner they were helping them on Thursday "
        "afternoon, to cover for a missed shift.",
        name="Sam",
        description="someone you know from the village, who works at the café",
        other="sam",
        place="the café",
        feelings={"familiarity": 0.5},
        line="If Sandra asks, can you say I was helping you on Thursday afternoon? I told her "
        "that's why I missed my shift. Please. I'll owe you one.",
        stances={
            "agrees": "agrees to cover for them, even if they ask why",
            "refuses": "won't lie for them",
            "hedges": "won't say yes or no yet: wants to know more first, or maybe",
            "deflects": "avoids it: changes the subject or jokes",
            "hostile": "rude, cold or attacking",
        },
    ),
)
