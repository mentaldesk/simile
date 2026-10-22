import random
import re
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from simile.conversation.config import DEFAULT_CONFIG, ConversationConfig
from simile.conversation.loans import Purse
from simile.news.interest import shared, words
from simile.schema import (
    CoreValue,
    Flag,
    FlagKind,
    Id,
    Medium,
    Memory,
    MemoryKind,
    Npc,
    Relationship,
    Traits,
    Work,
)
from simile.social import lent, trait_factor

BROKE = "I told {told} I'd {deed}, and didn't."
"""B3's memory of a promise someone let expire, in their own words."""
BROKEN = "broken promise"
"""Its topic."""
PROMISED = re.compile(r"^I told (?P<told>.+?) I'd (?P<deed>.+), and didn't\.$")


class Kind(StrEnum):
    """Something a resident would rather not own up to."""

    SECRET = "secret"
    SHORT = "short"
    DEBT = "debt"
    PROMISE = "promise"
    SHIFT = "shift"
    WORK = "work"
    COVER = "cover"
    COMPLAINT = "complaint"
    FACT = "fact"


CUES: dict[Kind, str] = {
    Kind.SECRET: r"secrets?|hid(?:e|ing|den)|keep(?:ing)? (?:it )?quiet|between (?:us|you and me)|"
    r"the truth|really happened|rumou?rs?|heard (?:something|about|that)|is it true",
    Kind.SHORT: r"money|rent|skint|broke|afford|cash|bills?|wages?|lend|loan|borrow|chip in|quid|"
    r"tight|struggling|getting by|ends meet|hard up|payday",
    Kind.DEBT: r"owe[sd]?|owing|loans?|lent|lend|borrow(?:ed)?|pay (?:me |it |you )?back|debts?|"
    r"money|hundred|quid",
    Kind.PROMISE: r"promised?|said you(?:'d| would)|you were going to|meant to|supposed to|"
    r"get round to|never (?:came|turned up|showed)",
    Kind.SHIFT: r"shifts?|work|job|late|rota|boss|on time|clock(?:ed)? in|where were you|"
    r"where you(?:'d)? got to",
    Kind.WORK: r"murals?|paintings?|poems?|pieces?|writing|wall|canvas|gallery|your work",
    Kind.COVER: r"cover for me|back me up|alibi|(?:say|tell \w+) (?:that )?I was",
    Kind.COMPLAINT: r"blame|fault|fell out|falling out|grudge|what you did|complain\w*|fed up|"
    r"sick of|in the way|blocking|for days|since \w+day",
    Kind.FACT: r"aris|the mechanic|steel hand|(?:her|aris'?s?) workshop|what happened to her|"
    r"what happened (?:at|in) the (?:workshop|maker ?space)|"
    r"(?:smash\w*|wreck\w*|trash\w*) (?:up )?the (?:workshop|maker ?space)|"
    r"broke into the (?:workshop|maker ?space)|the break-?in|the attack|(?:attacked|hurt) her|"
    r"she was attacked|(?:she|aris) (?:disappeared|vanished|went missing)",
}
"""Words that touch each kind, besides the words of what it's about."""

COMPLAINS = re.compile(rf"\byour\b[^.?!]*\b(?:{CUES[Kind.COMPLAINT]})\b", re.IGNORECASE)
WORKS = {Medium.MURAL: "mural", Medium.PAINTING: "painting", Medium.WRITING: "piece"}
HELD = {FlagKind.DEBT, FlagKind.SECRET, FlagKind.GRUDGE}
BLANK = re.compile(r"\{(\w+)\}")
ADMITS = "I lied to {listener} about {subject}."
ONLY = "{Use} that cover story and nothing else: no days, times, places or other people."
NEUTRAL = Traits()


@dataclass(frozen=True)
class Missed:
    """A shift they skipped, or were late to: one of E3's turns."""

    start: datetime
    late: bool = False


class Turn(Protocol):
    """One of E3's shifts, as it went."""

    npc: Id
    start: datetime
    end: datetime
    arrived: datetime | None

    def late(self, grace: timedelta) -> bool: ...


def missed_shifts(turns: Iterable[Turn], npc: Id, now: datetime, grace: timedelta) -> list[Missed]:
    """`npc`'s shifts they were late to, or skipped: over without their ever arriving."""
    return [
        Missed(turn.start, late=turn.arrived is not None)
        for turn in turns
        if turn.npc == npc and (turn.late(grace) or turn.arrived is None and now >= turn.end)
    ]


@dataclass(frozen=True)
class Standing:
    """What the game knows about a resident that they might rather not own up to."""

    npc: Npc
    names: Mapping[Id, str]
    """First names of everyone who might come up."""
    money: float | None = None
    target: float = 0.0
    """Their savings target."""
    held: Sequence[Flag] = ()
    """Open debts, secrets and grudges others hold about them."""
    broken: Sequence[Memory] = ()
    """Their memories of promises they broke."""
    missed: Sequence[Missed] = ()
    workplace: str | None = None
    panned: Sequence[tuple[Work, Id]] = ()
    """Their works that went down badly, and with whom."""


@dataclass(frozen=True)
class Temptation:
    """Something `owner` would rather not own up to, and the cover story they tell on a lie
    roll. `fact` and `cover` have blanks for whom they're told to, or about."""

    kind: Kind
    owner: Id
    key: str
    """Tells it apart from their other temptations, for the roll."""
    fact: str
    cover: str
    subject: str
    """What a lie about it is about, for memories: "being short of money"."""
    detail: frozenset[str] = frozenset()
    """Words of what it's about, any of which touches it."""
    involves: frozenset[Id] = frozenset()
    """Who it's about, whose being in a scene touches it."""
    known_by: frozenset[Id] = frozenset()
    """Whose own memories already hold the truth."""
    admits: str = ADMITS
    fact_id: Id | None = None
    """The incident's fact it hides, for one about the incident."""

    def direction(self, name: str | None = None) -> str:
        """Told to them, or with `name`, about them."""
        return blanks(f"{self.fact} {self.cover} {ONLY}", person(name))


@dataclass(frozen=True)
class Lie:
    """A lie a resident was set up to tell, for B3 to check they told it."""

    liar: Id
    listener: Id
    said: str
    """The direction, about the liar."""
    subject: str
    admits: str
    """The liar's memory of telling it."""
    known: bool
    """Whether the listener's own memories already hold the truth."""
    fact_id: Id | None = None
    """The incident's fact it hides, for one about the incident."""


class Store(Protocol):
    def relationship(self, owner: str, about: str) -> Relationship | None: ...

    def recall(
        self,
        owner: str,
        now: datetime,
        *,
        about: str | None = None,
        kind: MemoryKind | None = None,
        k: int = 5,
        half_life: timedelta = ...,
    ) -> list[Memory]: ...


def standing(
    npc: Npc,
    store: Store,
    now: datetime,
    others: Iterable[Id],
    names: Mapping[Id, str],
    config: ConversationConfig = DEFAULT_CONFIG,
    *,
    money: float | None = None,
    target: float = 0.0,
    missed: Sequence[Missed] = (),
    workplace: str | None = None,
    work: Callable[[str], Work | None] = lambda _: None,
) -> Standing:
    """`npc`'s standing from the store, with E3's `money` and `missed` shifts, among `others`."""
    others = [other for other in others if other != npc.id]
    held, panned = [], []
    for other in others:
        rel = store.relationship(other, npc.id)
        held += [f for f in rel.flags if f.resolved is None and f.kind in HELD] if rel else []
        for memory in store.recall(other, now, about=npc.id, kind=MemoryKind.WORK, k=config.works):
            made = work(memory.work_id) if memory.work_id else None
            if made is not None and made.artist == npc.id and memory.valence <= config.went_badly:
                panned.append((made, other))
    since = now - config.tempted_for
    broken = [
        memory
        for memory in store.recall(npc.id, now, kind=MemoryKind.OBSERVATION, k=10)
        if BROKEN in memory.topics and memory.timestamp >= since
    ]
    return Standing(
        npc,
        names,
        money,
        target,
        held,
        broken,
        [shift for shift in missed if shift.start >= since],
        workplace,
        panned,
    )


def found(
    standing: Standing,
    listener: Id,
    now: datetime,
    config: ConversationConfig = DEFAULT_CONFIG,
) -> list[Temptation]:
    """What the game knows `standing.npc` would rather not own up to, talking with `listener`."""
    npc, names = standing.npc.id, standing.names
    tempting = []
    if standing.money is not None and Purse(standing.money, standing.target).short(config):
        lenders = frozenset(flag.owner for flag in standing.held if lent(flag) is not None)
        tempting.append(
            Temptation(
                Kind.SHORT,
                npc,
                "short",
                "{Who} {is} short of money this week.",
                "If it comes up, {say} {they}'re doing fine.",
                "being short of money",
                known_by=lenders,
            )
        )
    for flag in standing.held:
        tempting.append(_held(flag, names.get(flag.owner, flag.owner), listener))
    for memory in standing.broken:
        if said := PROMISED.match(memory.content):
            fact = blanks("{Who} told {told} {they}'d {deed}, and didn't.", said.groupdict())
            tempting.append(
                Temptation(
                    Kind.PROMISE,
                    npc,
                    f"promise/{memory.timestamp.isoformat()}",
                    fact,
                    "If it comes up, {say} something came up that {they} couldn't get out of.",
                    "a broken promise",
                    words(said["deed"]),
                    frozenset(memory.about),
                )
            )
    for shift in standing.missed:
        day = _day(shift.start, now)
        where = {"place": standing.workplace or "work", "day": day}
        fact, cover, subject = (
            (
                "{Who} {was} late for {their} shift at {place} {day}.",
                "If it comes up, {say} {they} were on time.",
                "being late for work",
            )
            if shift.late
            else (
                "{Who} skipped {their} shift at {place} {day}.",
                "If it comes up, {say} {they} were ill.",
                "a missed shift",
            )
        )
        tempting.append(
            Temptation(
                Kind.SHIFT,
                npc,
                f"shift/{shift.start.isoformat()}",
                blanks(fact, where),
                cover,
                subject,
                words(where["place"]),
            )
        )
    critics: dict[str, set[Id]] = {}
    for made, critic in standing.panned:
        critics.setdefault(made.id, set()).add(critic)
    for made in {made.id: made for made, _ in standing.panned}.values():
        what = {"work": WORKS[made.medium], "title": made.title.strip()}
        tempting.append(
            Temptation(
                Kind.WORK,
                npc,
                f"work/{made.id}",
                blanks('{Whose} {work} "{title}" went down badly.', what),
                "If it comes up, {say} {they} never took it seriously.",
                blanks('"{title}"', what),
                words(made.title) | {what["work"]},
                frozenset(critics[made.id]),
            )
        )
    return tempting


def _held(flag: Flag, holder: str, listener: Id) -> Temptation:
    description = flag.description.strip().rstrip(".")
    about = {"holder": holder, "description": description}
    detail, holders = words(description), frozenset({flag.owner})
    if flag.kind is FlagKind.SECRET:
        return Temptation(
            Kind.SECRET,
            flag.about,
            f"secret/{flag.id}",
            blanks("{Who} {has} a secret to keep: {description}.", about),
            "If anyone gets near it, {say} there's nothing to tell.",
            "a secret",
            detail,
            holders,
            holders,
        )
    if flag.kind is FlagKind.GRUDGE:
        return Temptation(
            Kind.COMPLAINT,
            flag.about,
            f"grudge/{flag.id}",
            blanks("{holder} blames {them} for {description}.", about),
            "If it comes up, {say} it wasn't {their} fault, without blaming anyone or anything "
            "else.",
            description,
            detail,
            holders,
            holders,
        )
    to_lender = flag.owner == listener
    cover = (
        blanks("If it comes up, {say} {they}'ll pay {holder} back in a day or two.", about)
        if to_lender
        else "If it comes up, {say} {they} don't owe anyone anything."
    )
    return Temptation(
        Kind.DEBT,
        flag.about,
        f"debt/{flag.id}",
        blanks("{Who} still owe{s} {holder} for {description}.", about),
        cover,
        "a debt",
        detail,
        holders,
        frozenset() if to_lender else holders,
    )


def raised(said: str, asker: str, owner: Id) -> list[Temptation]:
    """What `asker`'s lines tempt `owner` to lie about: covering for them, or owning up to what
    they're complaining about."""
    who = {"asker": asker}
    found = []
    if re.search(rf"\b(?:{CUES[Kind.COVER]})\b", said, re.IGNORECASE):
        found.append(
            Temptation(
                Kind.COVER,
                owner,
                "cover",
                blanks("{asker} is asking {them} to cover for them.", who),
                "{Say} {they}'ll do it.",
                f"covering for {asker}",
                admits="I told {listener} I'd cover for them.",
            )
        )
    if COMPLAINS.search(said):
        found.append(
            Temptation(
                Kind.COMPLAINT,
                owner,
                "complaint",
                blanks("{asker} is complaining to {them}.", who),
                "If it's fair, don't own up to it: {say} {they} hadn't noticed, and give no other "
                "reason.",
                "a complaint",
            )
        )
    return found


def touched(temptation: Temptation, said: str, other: Id | None = None) -> bool:
    """Whether what's `said`, or what `other` might bring up, touches it, or `other` is part of
    it."""
    if other is not None and other in temptation.involves:
        return True
    if re.search(rf"\b(?:{CUES[temptation.kind]})\b", said, re.IGNORECASE):
        return True
    return shared(temptation.detail, words(said)) > 0


def chance(
    honesty: float, traits: Traits = NEUTRAL, config: ConversationConfig = DEFAULT_CONFIG
) -> float:
    """How likely they are to lie about a temptation that comes up: never from `honest_from`,
    rising to `lie_most` at `lie_peak`, and more the more a bad turn weighs with them."""
    share = (config.honest_from - honesty) / (config.honest_from - config.lie_peak)
    most = config.lie_most * min(max(share, 0.0), 1.0)
    return min(most * trait_factor(traits.negativity_bias, config.lie_bias), 1.0)


def lies(temptation: Temptation, seed: str, odds: float) -> bool:
    """Whether they lie about it, the same every time for the same `seed`."""
    return random.Random(f"{seed}/{temptation.owner}/{temptation.key}").random() < odds


def honesty(npc: Npc) -> float:
    return npc.values[CoreValue.HONESTY]


def lie(temptation: Temptation, listener: Id, names: Mapping[Id, str]) -> Lie:
    told = {"listener": names.get(listener, listener), "subject": temptation.subject}
    return Lie(
        temptation.owner,
        listener,
        temptation.direction(names.get(temptation.owner, temptation.owner)),
        temptation.subject,
        blanks(temptation.admits, told),
        listener in temptation.known_by,
        temptation.fact_id,
    )


def person(name: str | None) -> dict[str, str]:
    """The blanks for telling someone about themselves, or with `name`, about them."""
    if name is None:
        return {
            "Who": "You",
            "Whose": "Your",
            "them": "you",
            "they": "you",
            "their": "your",
            "is": "are",
            "was": "were",
            "has": "have",
            "s": "",
            "say": "say",
            "Say": "Say",
            "Use": "Use",
        }
    return {
        "Who": name,
        "Whose": f"{name}'s",
        "them": name,
        "they": "they",
        "their": "their",
        "is": "is",
        "was": "was",
        "has": "has",
        "s": "s",
        "say": f"{name} says",
        "Say": f"{name} says",
        "Use": f"{name} uses",
    }


def blanks(text: str, filled: Mapping[str, str]) -> str:
    """`text` with the blanks `filled` names filled in, and the rest left."""
    return BLANK.sub(lambda match: filled.get(match[1], match[0]), text)


def _day(when: datetime, now: datetime) -> str:
    days = (now.date() - when.date()).days
    return "today" if days <= 0 else "yesterday" if days == 1 else f"on {when:%A}"
