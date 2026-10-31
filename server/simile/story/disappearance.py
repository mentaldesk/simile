import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta

from simile.schema import (
    ARIS,
    CoreValue,
    Disappearance,
    Fact,
    HowKnown,
    Id,
    Key,
    Knower,
    Lead,
    Memory,
    MemoryKind,
    Npc,
)
from simile.social import tolerance
from simile.social.bionics import level
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.content import HATCH, NOTES, TERMINAL, StoryContent, load_story

GONE = "gone"
NOTED = "notes"
DISTRUST = "distrust_"
LAST_SEEN = "last_seen"
PASSED = "passed"
LIFT_LOG = "lift_log"
HATCH_LOG = "hatch_log"
TOPIC = "aris"

WHAT_GONE = (
    "One morning Aris's workshop was found standing open, her tea cold and her tools left on the "
    "bench as if she'd stepped out. Nobody saw her leave."
)
METRO = "She was heading for the old metro. See whether anything down there remembers her."
DOWN = "She was going down to the old metro. See whether anything down there remembers her."
EVENING = "the evening before she went missing"
SAW_HER = f"whether {{they}} saw Aris {EVENING}"
READ = "Her notes are still on the workshop bench. Read what she wrote last."


def distrust(npc: Id) -> Id:
    return f"{DISTRUST}{npc}"


def question(fact_id: Id, how: HowKnown) -> str:
    """What someone has to ask before a knower gives their cover story for a fact."""
    if fact_id.startswith(DISTRUST):
        did = how is HowKnown.DID
        return "how {they} got on with Aris" if did else "what {they} heard said about Aris"
    if fact_id in (LAST_SEEN, PASSED):
        return SAW_HER
    return "what happened to Aris"


def initial(name: str) -> str:
    return name.strip()[:1].upper()


def street_name(street: Key) -> str:
    return street.replace("_", " ").title()


@dataclass(frozen=True)
class Made:
    """A disappearance and every resident's memories of it, which the store doesn't hold yet."""

    disappearance: Disappearance
    memories: list[Memory]


@dataclass
class _Building:
    npcs: dict[Id, Npc]
    content: StoryContent
    config: StoryConfig
    facts: list[Fact] = field(default_factory=list)
    remembered: dict[tuple[Id, Id], str] = field(default_factory=dict)

    def name(self, npc: Id) -> str:
        return self.npcs[npc].name.split()[0]

    def add(self, fact: Fact, remembered: dict[Id, str]) -> Fact:
        self.facts.append(fact)
        for npc, text in remembered.items():
            self.remembered[(fact.id, npc)] = text
        return fact

    def witness(self, npc: Id, part: Id) -> Knower:
        """A witness, as wary as their values make them, who lies if they're dishonest."""
        config, values = self.config, self.npcs[npc].values
        wary = 0.5 + sum(w * (values[value] - 0.5) for value, w in config.tells_from.items())
        honest = values[CoreValue.HONESTY] >= config.witness_lies_below
        return Knower(
            id=npc,
            how=HowKnown.WITNESSED,
            tells_from=round(min(max(wary, 0.0), config.most_wary), 2),
            cover=None if honest else self.content.texts.covers[part],
        )

    def lies(self, npc: Id) -> bool:
        return self.npcs[npc].values[CoreValue.HONESTY] < self.config.distruster_lies_below

    def distruster(self, npc: Id, how: HowKnown, cover: str) -> Knower:
        """A distruster: tells anyone if strongly against and honest, else lies if dishonest."""
        config, values = self.config, self.npcs[npc].values
        honest = not self.lies(npc)
        strongly = level(tolerance(values)) == -2
        return Knower(
            id=npc,
            how=how,
            tells_from=0.0 if strongly and honest else config.admits_from,
            cover=None if honest else cover,
        )


def distrusters(npcs: Sequence[Npc], config: StoryConfig = DEFAULT_CONFIG) -> list[Npc]:
    """Those at or past `distrusts_from`, least tolerant first, or else the least tolerant."""
    ranked = sorted(npcs, key=lambda npc: (tolerance(npc.values), npc.id))
    found = [npc for npc in ranked if level(tolerance(npc.values)) <= config.distrusts_from]
    return found or ranked[:1]


def build(
    npcs: Sequence[Npc],
    now: datetime,
    rng: random.Random,
    content: StoryContent,
    config: StoryConfig = DEFAULT_CONFIG,
) -> Made:
    """The disappearance among `npcs`, the day before `now`: its facts, clues and leads."""
    making = _Building({npc.id: npc for npc in npcs}, content, config)
    texts, memories = content.texts, content.texts.memories
    ids = [npc.id for npc in distrusters(npcs, config)]
    gone = (now - config.gone_before).replace(minute=0, second=0, microsecond=0)
    seen = _evening(gone - timedelta(days=1), config.seen_between, rng)
    others = [npc.id for npc in npcs if npc.id not in ids]
    bystanders = _bystanders(others, rng)
    passer = rng.choice([npc for npc in ids if making.lies(npc)] or ids)
    rest = [npc for npc in ids if npc != passer]
    noted = [passer, *rng.sample(rest, min(len(rest), rng.choice((0, 1))))]
    rng.shuffle(noted)
    seen_by = next(bystanders, None)
    passer_name = making.name(passer)
    street, last_seen = content.aris.street, content.aris.last_seen
    steps = f"{street_name(last_seen)}'s steps"

    making.add(lift_log(seen), {})
    making.add(hatch_log(seen), {})

    making.add(
        Fact(
            id=PASSED,
            what=f"{passer_name} passed Aris on {steps} that last evening as she went down "
            "towards the old metro, and said nothing to her.",
            when=seen,
            where=last_seen,
            about=[passer, ARIS],
            known_by=[making.distruster(passer, HowKnown.WITNESSED, texts.not_seen)],
            leads=[Lead(fact_id=LIFT_LOG, text=DOWN)],
        ),
        {passer: memories.passed.format(steps=steps)},
    )

    if seen_by is not None:
        at = f"{seen:%H:%M}"
        making.add(
            Fact(
                id=LAST_SEEN,
                what=f"{making.name(seen_by)} saw Aris heading down {steps} towards the old metro "
                f"at about {at} {EVENING}, with {passer_name} going the other way.",
                when=seen,
                where=last_seen,
                about=[ARIS, passer],
                known_by=[making.witness(seen_by, LAST_SEEN)],
                leads=[
                    Lead(fact_id=LIFT_LOG, text=METRO),
                    Lead(
                        fact_id=PASSED,
                        text=f"{passer_name} passed her on the steps. Ask {passer_name} "
                        f"about {EVENING}.",
                    ),
                ],
            ),
            {seen_by: memories.saw.format(time=at, name=passer_name, steps=steps)},
        )

    heard_by: dict[Id, Id | None] = {npc: next(bystanders, None) for npc in ids}
    for npc in ids:
        name, witness = making.name(npc), heard_by[npc]
        knowers = [making.distruster(npc, HowKnown.DID, texts.denial)]
        remembered = {npc: memories.distrusted}
        if witness is not None:
            knowers.append(making.witness(witness, "distrust"))
            remembered[witness] = memories.heard.format(name=name)
        making.add(
            Fact(
                id=distrust(npc),
                what=f"{name} distrusted Aris's bionics and said she wasn't one of them any more.",
                when=(seen - timedelta(days=rng.randint(2, 5))).replace(
                    hour=rng.randint(9, 17), minute=rng.choice((0, 15, 30, 45))
                ),
                where=street,
                about=[npc, ARIS],
                known_by=knowers,
                leads=[
                    Lead(
                        fact_id=PASSED,
                        text=f"{name} had no time for Aris. Ask {name} about {EVENING}.",
                    )
                ]
                if npc == passer
                else [],
            ),
            remembered,
        )

    lines = rng.sample(texts.notes, len(noted))
    notes = making.add(
        Fact(
            id=NOTED,
            what="Aris wrote in her notebook: "
            + " ".join(
                f'"{line.format(initial=initial(making.npcs[npc].name))}"'
                for npc, line in zip(noted, lines, strict=True)
            ),
            when=(seen - timedelta(days=1)).replace(hour=21, minute=0),
            where=content.aris.workshop,
            about=[ARIS, *noted],
            known_by=[],
            found_in=NOTES,
            leads=[_ask_how(making, npc, heard_by[npc]) for npc in noted],
        ),
        {},
    )

    everyone = [npc.id for npc in npcs]
    leads = [Lead(fact_id=notes.id, text=READ)]
    if seen_by is not None:
        witness = making.name(seen_by)
        leads.append(
            Lead(
                fact_id=LAST_SEEN,
                text=f"{witness} saw her {EVENING}. Ask {witness} where she was going.",
            )
        )
    making.add(
        Fact(
            id=GONE,
            what=WHAT_GONE,
            when=gone,
            where=content.aris.workshop,
            about=[ARIS],
            known_by=[
                Knower(id=npc, how=HowKnown.TOLD, tells_from=0.0, cover=None) for npc in everyone
            ],
            leads=leads,
        ),
        {npc: f"{WHAT_GONE} {texts.relieved}" if npc in ids else WHAT_GONE for npc in everyone},
    )

    order = [GONE, NOTED, *map(distrust, ids), LAST_SEEN, PASSED, LIFT_LOG, HATCH_LOG]
    facts = sorted(making.facts, key=lambda fact: order.index(fact.id))
    disappearance = Disappearance(distrusted_by=ids, facts=facts)
    return Made(disappearance, _memories(making, set(ids)))


def lift_log(seen: datetime) -> Fact:
    """The fact in the metro's dead terminal, logged just after Aris was last seen."""
    return Fact(
        id=LIFT_LOG,
        what="The dead terminal in the old metro carries Aris's maker's mark: she rewired it. Its "
        "last entry logs the maintenance lift going down to the sewers the night before her "
        "workshop was found standing open.",
        when=seen + timedelta(minutes=15),
        where="metro",
        about=[ARIS],
        known_by=[],
        found_in=TERMINAL,
        leads=[
            Lead(
                fact_id=HATCH_LOG,
                text="The lift went down to the sewers. Take it down and find where she went.",
            )
        ],
    )


def hatch_log(seen: datetime) -> Fact:
    """The fact in the sewers' maintenance hatch, an hour after the lift went down."""
    return Fact(
        id=HATCH_LOG,
        what="A maintenance hatch deep in the sewers is stamped with Apex's mark, and its lock "
        "carries Aris's maker's mark: she wired a key of her own into it. Its log shows that key "
        "opening it the night before her workshop was found standing open, onto a shaft that "
        "climbs towards the Apex towers.",
        when=seen + timedelta(minutes=75),
        where="sewers",
        about=[ARIS],
        known_by=[],
        found_in=HATCH,
    )


def logged(disappearance: Disappearance) -> bool:
    """Brings both logs up to date with when she was last seen. Whether they changed."""
    facts = {fact.id: fact for fact in disappearance.facts}
    if PASSED not in facts:
        return False
    seen = facts[PASSED].when
    wanted = [lift_log(seen), hatch_log(seen)]
    if all(facts.get(fact.id) == fact for fact in wanted):
        return False
    kept = [fact for fact in disappearance.facts if fact.id not in (LIFT_LOG, HATCH_LOG)]
    disappearance.facts = [*kept, *wanted]
    return True


def _ask_how(making: _Building, npc: Id, heard_by: Id | None) -> Lead:
    who = f"{initial(making.npcs[npc].name)}."
    if heard_by is None:
        return Lead(
            fact_id=distrust(npc),
            text=f"Who's {who}? Find out, and ask how they got on with Aris.",
        )
    witness = making.name(heard_by)
    return Lead(
        fact_id=distrust(npc),
        text=f"Who's {who}? {witness} might know. Ask {witness} what's been said about Aris.",
    )


def _memories(making: _Building, relieved: set[Id]) -> list[Memory]:
    config = making.config
    memories = []
    for fact in making.facts:
        for knower in fact.known_by:
            glad = fact.id == GONE and knower.id in relieved
            memories.append(
                Memory(
                    owner=knower.id,
                    kind=MemoryKind.OBSERVATION,
                    content=making.remembered[(fact.id, knower.id)],
                    salience=config.salience[knower.how],
                    valence=config.relieved if glad else config.valence[knower.how],
                    timestamp=fact.when,
                    about=[who for who in fact.about if who != knower.id],
                    topics=[TOPIC],
                    fact_id=fact.id,
                )
            )
    return memories


def _evening(day: datetime, between: tuple[time, time], rng: random.Random) -> datetime:
    start, end = (t.hour * 60 + t.minute for t in between)
    minutes = rng.randrange(start, end + 1, 5) if end > start else start
    return day.replace(hour=minutes // 60, minute=minutes % 60, second=0, microsecond=0)


def _bystanders(npcs: list[Id], rng: random.Random) -> Iterator[Id]:
    """Residents to witness each part, each once before anyone twice."""
    if not npcs:
        return
    while True:
        round_ = sorted(npcs)
        rng.shuffle(round_)
        yield from round_


def make_disappearance(
    npcs: Sequence[Npc],
    now: datetime,
    *,
    rng: random.Random | None = None,
    content: StoryContent | None = None,
    config: StoryConfig = DEFAULT_CONFIG,
) -> Made:
    """A new disappearance among `npcs`, and their memories of it."""
    return build(npcs, now, rng or random.Random(), content or load_story(), config)
