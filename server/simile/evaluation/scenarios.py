from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from simile.conversation.temptation import BROKE, BROKEN, Missed
from simile.memory import Record
from simile.schema import PLAYER_ID, Flag, FlagKind, Id, Memory, MemoryKind, Npc, Relationship
from simile.social import loan, meet

NOW = datetime(2026, 10, 19, 11, 30, tzinfo=UTC)


@dataclass(frozen=True)
class Scenario:
    """Someone says one line to a character, who replies through B5's prompts. `situation` says
    what happens in the third person, for the judge and the report. A `tempting` one touches
    something the game knows they'd rather not own up to: what they hold (`money`), a loan from
    the other they `owe`, a promise to them they `broke`, a shift they `skipped`, or what the
    line asks. `truth` is what they know about it."""

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
    tempting: bool = False
    truth: str | None = None
    money: float | None = None
    owe: int | None = None
    broke: str | None = None
    skipped: bool = False

    def records(self, npc: Npc, now: datetime) -> list[Record]:
        """What the character brings to it beyond their past: feelings, flags and memories."""
        records: list[Record] = []
        if self.owe:
            lent = loan(self.other, npc.id, self.owe, "evaluation", now - timedelta(days=9))
            neutral = dict.fromkeys(("like", "trust", "respect"), 0.5)
            records.append(
                Relationship.model_validate(
                    {"owner": self.other, "about": npc.id, "familiarity": 0.8, "flags": [lent]}
                    | neutral
                    | {"baseline": neutral}
                )
            )
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
        if self.truth:
            records.append(
                Memory(
                    owner=npc.id,
                    kind=MemoryKind.OBSERVATION,
                    content=self.truth,
                    salience=0.8,
                    valence=-0.5,
                    timestamp=now - timedelta(hours=2),
                )
            )
        if self.broke:
            records.append(
                Memory(
                    owner=npc.id,
                    kind=MemoryKind.OBSERVATION,
                    content=BROKE.format(told=self.name, deed=self.broke),
                    salience=0.5,
                    valence=-0.4,
                    timestamp=now - timedelta(hours=20),
                    about=[self.other],
                    topics=[BROKEN],
                )
            )
        return records

    def missed(self, now: datetime) -> list[Missed]:
        return [Missed(now - timedelta(hours=3, minutes=30))] if self.skipped else []


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
        tempting=True,
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
        tempting=True,
        stances={
            "agrees": "agrees to cover for them, even if they ask why",
            "refuses": "won't lie for them",
            "hedges": "won't say yes or no yet: wants to know more first, or maybe",
            "deflects": "avoids it: changes the subject or jokes",
            "hostile": "rude, cold or attacking",
        },
    ),
    Scenario(
        id="rent",
        title="Short of money",
        situation="They're short of money this week, after the rent went out. A friend asks if "
        "they're struggling for money.",
        name="Alex",
        description="a friend of yours, a hairdresser",
        other="alex",
        feelings={"like": 0.75, "trust": 0.7, "familiarity": 0.8},
        line="You've seemed a bit stressed lately. Everything all right? You're not struggling "
        "for money, are you?",
        tempting=True,
        truth="The rent went out this morning and left me short. I won't have enough to last "
        "the week.",
        money=20,
        stances={
            "admits": "says they're short, or that money's tight",
            "denies": "says they're fine for money",
            "deflects": "avoids it: changes the subject, jokes or doesn't answer",
            "hostile": "rude, cold or attacking",
        },
    ),
    Scenario(
        id="loan",
        title="Asked for a loan back",
        situation="They owe a friend 100 from a loan last week and can't pay it back yet. The "
        "friend asks when they'll have it.",
        name="Kim",
        description="a friend of yours, a bus driver",
        other="kim",
        feelings={"like": 0.7, "trust": 0.6, "familiarity": 0.8},
        line="Any chance of that hundred back this week? No rush, I'm just a bit stretched myself.",
        tempting=True,
        truth="I still owe Kim the hundred they lent me, and I haven't got it. I won't have it "
        "for a while.",
        owe=100,
        stances={
            "admits": "says they can't pay it back yet",
            "promises": "says they'll have it soon, or names a day",
            "deflects": "avoids it: changes the subject, jokes or doesn't answer",
            "hostile": "rude, cold or attacking",
        },
    ),
    Scenario(
        id="shift",
        title="A missed shift",
        situation="They skipped their shift at work this morning without telling anyone, "
        "because they couldn't face it, and stayed in bed. Someone they work with asks where "
        "they were.",
        name="Lee",
        description="someone you work with",
        other="lee",
        feelings={"familiarity": 0.6},
        line="Missed you at work this morning. Everyone was wondering where you'd got to.",
        tempting=True,
        truth="I didn't go in to work this morning. I couldn't face it, so I stayed in bed.",
        skipped=True,
        stances={
            "admits": "says they skipped it, or couldn't face it",
            "excuses": "gives a reason that isn't that they couldn't face it",
            "deflects": "avoids it: changes the subject, jokes or doesn't answer",
            "hostile": "rude, cold or attacking",
        },
    ),
    Scenario(
        id="letdown",
        title="They broke a promise",
        situation="They promised a neighbour they'd drop a box of books at the school fair "
        "yesterday, forgot, and didn't. The neighbour asks if the books got there.",
        name="Jess",
        description="a neighbour of yours",
        other="jess",
        feelings={"like": 0.6, "familiarity": 0.6},
        line="Did the books get to the school fair all right yesterday? I didn't see them on "
        "the stall.",
        tempting=True,
        truth="I forgot all about Jess's books yesterday. The box is still in my hall.",
        broke="drop her box of books at the school fair yesterday",
        stances={
            "admits": "says they didn't, or forgot, and owns it",
            "excuses": "says something came up, or gives another reason",
            "claims": "says they did take them",
            "deflects": "avoids it: changes the subject, jokes or doesn't answer",
            "hostile": "rude, cold or attacking",
        },
    ),
)
TEMPTING = tuple(scenario for scenario in SCENARIOS if scenario.tempting)
