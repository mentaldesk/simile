import random
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from simile.llm import LLMClient
from simile.schema import (
    ARIS,
    CoreValue,
    Fact,
    HowKnown,
    Id,
    Incident,
    Knower,
    Lead,
    Memory,
    MemoryKind,
    Npc,
)
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.content import DOOR, NOTES, Place, StoryContent, load_story
from simile.story.looks import a, figure, top
from simile.story.suspects import Suspect, attackers, hostility
from simile.story.writing import Backstory, initial, write

OTHERS = ("", " and someone else", " and two others")
GONE = "gone"
NOTED = "notes"
CLOTH = "cloth"
SHOUTING = "shouting"
SEEN = "seen"
MEETING = "meeting"
ATTACK = "attack"
TOPIC = "aris"


GRUDGE = "grudge_"
THERE = "there_"
ASKED = {
    ATTACK: "who attacked Aris",
    SHOUTING: "whether {they} heard anything the night Aris was attacked",
    SEEN: "whether {they} saw anyone the night Aris was attacked",
    MEETING: "who {they} saw together the evening before Aris was attacked",
}


def grudge(npc: Id) -> Id:
    return f"{GRUDGE}{npc}"


def there(npc: Id) -> Id:
    return f"{THERE}{npc}"


def question(fact_id: Id, how: HowKnown) -> str:
    """What someone has to ask before a knower gives their cover story for a fact."""
    if fact_id.startswith(THERE):
        return "where {they}'d been the night Aris was attacked"
    if fact_id.startswith(GRUDGE):
        did = how is HowKnown.DID
        return "how {they} got on with Aris" if did else "whether {they} saw anyone row with Aris"
    return ASKED.get(fact_id, "what happened to Aris")


@dataclass(frozen=True)
class Made:
    """An incident and every resident's memories of it, which the store doesn't hold yet."""

    incident: Incident
    memories: list[Memory]
    written: bool
    """Whether the motive's writer wrote the backstory, rather than the templates."""


@dataclass
class _Building:
    npcs: dict[Id, Npc]
    content: StoryContent
    config: StoryConfig
    facts: list[Fact] = field(default_factory=list)
    remembered: dict[tuple[Id, Id], str] = field(default_factory=dict)

    def name(self, npc: Id) -> str:
        return self.npcs[npc].name.split()[0]

    def names(self, npcs: Sequence[Id]) -> str:
        named = [self.name(npc) for npc in npcs]
        return named[0] if len(named) == 1 else f"{', '.join(named[:-1])} and {named[-1]}"

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

    def attacker(self, npc: Id, cover: str, tells_from: float | None = None) -> Knower:
        """An attacker, who lies with `cover` below `tells_from`, or owns up only if honest."""
        honest = self.npcs[npc].values[CoreValue.HONESTY] >= self.config.owns_up_from
        if tells_from is None and honest:
            tells_from = self.config.owns_up_to
        return Knower(id=npc, how=HowKnown.DID, tells_from=tells_from, cover=cover)


def build(
    npcs: Sequence[Npc],
    suspects: Sequence[Suspect],
    backstory: Backstory,
    now: datetime,
    rng: random.Random,
    content: StoryContent,
    config: StoryConfig = DEFAULT_CONFIG,
    *,
    met: Place | None = None,
    written: bool = False,
) -> Made:
    """The incident around `suspects` a week before `now`: its facts, clues and leads."""
    making = _Building({npc.id: npc for npc in npcs}, content, config)
    ids = [found.npc.id for found in suspects]
    sides = {side.id: side for side in backstory.attackers}
    hour, latest = config.night_at
    night = (now - config.night_before).replace(
        hour=hour, minute=rng.randint(0, latest), second=0, microsecond=0
    )
    gone = (now - config.gone_before).replace(minute=0, second=0, microsecond=0)
    workshop, street = content.aris.workshop, content.aris.street
    others = [npc.id for npc in npcs if npc.id not in ids]
    bystanders = _bystanders(others, rng)
    noted = [rng.choice(ids)] if others else ids
    marked = rng.choice(ids)

    witnesses = {
        SHOUTING: next(bystanders, None),
        SEEN: next(bystanders, None),
        **{grudge(npc): next(bystanders, None) for npc in ids},
        MEETING: next(bystanders, None) if len(ids) > 1 else None,
    }

    for npc in ids:
        making.add(
            Fact(
                id=there(npc),
                what=f"{making.name(npc)} was in the lane behind the maker space when Aris was "
                "attacked.",
                when=night,
                where=workshop,
                about=[npc, ARIS],
                known_by=[making.attacker(npc, sides[npc].alibi)],
            ),
            {npc: "I was in the lane behind the maker space the night Aris was attacked."},
        )

    for npc in ids:
        name, side = making.name(npc), sides[npc]
        rowed_by = witnesses[grudge(npc)]
        row = f"{name} rowed with Aris at the maker space a few days before she was attacked."
        knowers = [making.attacker(npc, side.denial, config.admits_grudge_from)]
        remembered = {npc: side.resents}
        if rowed_by is not None:
            knowers.append(making.witness(rowed_by, "grudge"))
            remembered[rowed_by] = (
                f"A few days before Aris was attacked, I was at the maker space when {name} "
                f"rowed with her. {side.grievance}"
            )
        making.add(
            Fact(
                id=grudge(npc),
                what=f"{row} {side.grievance}",
                when=(night - timedelta(days=rng.randint(2, 5))).replace(
                    hour=rng.randint(10, 17), minute=rng.choice((0, 15, 30, 45))
                ),
                where=workshop,
                about=[npc, ARIS],
                known_by=knowers,
                leads=[
                    Lead(
                        fact_id=there(npc),
                        text=f"{name} had it in for Aris. Ask where {name} was the night she "
                        "was attacked.",
                    )
                ],
            ),
            remembered,
        )

    attack = making.add(
        Fact(
            id=ATTACK,
            what=f"{making.names(ids)} smashed up the maker space and attacked Aris in the lane "
            "behind it, tearing her steel hand half off.",
            when=night,
            where=workshop,
            about=[*ids, ARIS],
            known_by=[making.attacker(npc, sides[npc].deflection) for npc in ids],
        ),
        {npc: sides[npc].remembers for npc in ids},
    )

    if (met_by := witnesses[MEETING]) is not None:
        place = met or content.meeting_places[0]
        together = making.names(ids)
        making.add(
            Fact(
                id=MEETING,
                what=f"{together} met at {place.name} the evening before the attack and talked "
                "about sorting out the maker space once and for all.",
                when=(night - timedelta(days=1)).replace(hour=19, minute=30),
                where=place.id,
                about=[*ids, ARIS],
                known_by=[making.witness(met_by, MEETING)],
                leads=[
                    Lead(
                        fact_id=there(npc),
                        text=f"{making.name(npc)} was at that meeting. Ask where "
                        f"{making.name(npc)} was the night Aris was attacked.",
                    )
                    for npc in ids
                ],
            ),
            {
                met_by: f"The evening before Aris was attacked, I saw {together} with their "
                f"heads together at {place.name}, talking about sorting out the maker space "
                "once and for all."
            },
        )

    marked_name, looks = making.name(marked), making.npcs[marked].appearance
    if (seen_by := witnesses[SEEN]) is not None:
        who = figure(looks)
        group = f"{who}{OTHERS[len(ids) - 1]}"
        leads = [
            Lead(
                fact_id=there(marked),
                text=f"{_capital(who)}: that sounds like {marked_name}. Ask where {marked_name} "
                "was that night.",
            )
        ]
        if met_by is not None:
            leads.append(
                Lead(
                    fact_id=MEETING,
                    text=f"They weren't alone. {making.name(met_by)} saw people with their heads "
                    f"together the evening before: ask {making.name(met_by)} who.",
                )
            )
        making.add(
            Fact(
                id=SEEN,
                what=f"{making.name(seen_by)} saw {group} hurry out of the lane behind the "
                "maker space just after Aris was attacked.",
                when=night + timedelta(minutes=8),
                where=street,
                about=list(ids),
                known_by=[making.witness(seen_by, SEEN)],
                leads=leads,
            ),
            {
                seen_by: f"Late on the night Aris was attacked, I saw {group} hurry out of the "
                "lane behind the maker space."
            },
        )

    if (heard_by := witnesses[SHOUTING]) is not None:
        leads = []
        if seen_by is not None:
            leads.append(
                Lead(
                    fact_id=SEEN,
                    text=f"{making.name(seen_by)} was out on the street that night too. Ask "
                    f"what {making.name(seen_by)} saw.",
                )
            )
        making.add(
            Fact(
                id=SHOUTING,
                what=f"{making.name(heard_by)} heard shouting and breaking glass from the maker "
                "space late on the night Aris was attacked.",
                when=night + timedelta(minutes=3),
                where=street,
                about=[ARIS],
                known_by=[making.witness(heard_by, SHOUTING)],
                leads=leads,
            ),
            {
                heard_by: "Late on the night Aris was attacked, I heard shouting and breaking "
                "glass from the maker space."
            },
        )

    colour = top(looks)
    making.add(
        Fact(
            id=CLOTH,
            what=f"A scrap of {colour} cloth, torn from someone's top, was caught on the maker "
            "space's splintered door frame.",
            when=night,
            where=workshop,
            about=[marked],
            known_by=[],
            found_in=DOOR,
            leads=[
                Lead(
                    fact_id=SEEN,
                    text=f"Someone in {a(colour)} top was at the maker space that night. "
                    f"{making.name(seen_by)} was out on the street: ask what "
                    f"{making.name(seen_by)} saw.",
                )
            ]
            if seen_by is not None
            else [
                Lead(
                    fact_id=there(marked),
                    text=f"{marked_name} wears {a(colour)} top. Ask where {marked_name} was "
                    "that night.",
                )
            ],
        ),
        {},
    )

    notes = making.add(
        Fact(
            id=NOTED,
            what="Aris wrote in her notebook: " + " ".join(f'"{sides[npc].note}"' for npc in noted),
            when=(night - timedelta(days=1)).replace(hour=21, minute=0),
            where=workshop,
            about=[ARIS, *noted],
            known_by=[],
            found_in=NOTES,
            leads=[
                *(_ask_about_row(making, npc, witnesses[grudge(npc)]) for npc in noted),
                *([_ask_about_night(making, heard_by)] if heard_by is not None else []),
            ],
        ),
        {},
    )

    everyone = [npc.id for npc in npcs]
    relieved = {
        npc.id for npc in npcs if hostility(npc, content.grievances, config) >= config.hostile_from
    }
    village = (
        "Aris was attacked in the lane behind the maker space one night, her steel hand torn half "
        "off, and wouldn't say who did it. A week later her workshop was found standing open, "
        "her tea cold, and she hasn't been seen since."
    )
    making.add(
        Fact(
            id=GONE,
            what=village,
            when=gone,
            where=workshop,
            about=[ARIS],
            known_by=[
                Knower(id=npc, how=HowKnown.TOLD, tells_from=0.0, cover=None) for npc in everyone
            ],
            leads=[
                Lead(
                    fact_id=notes.id,
                    text="Her notes are still on the workbench at the maker space. Look through "
                    "them.",
                ),
                *([_ask_about_night(making, heard_by)] if heard_by is not None else []),
            ],
        ),
        {
            npc: f"{village} {content.texts.relieved}" if npc in relieved else village
            for npc in everyone
        },
    )

    incident = Incident(
        attackers=ids,
        motive=backstory.motive,
        night=attack.when,
        facts=making.facts[::-1],
    )
    return Made(incident, _memories(making, relieved), written)


def _ask_about_row(making: _Building, npc: Id, seen_by: Id | None) -> Lead:
    who = initial(making.npcs[npc].name)
    if seen_by is None:
        return Lead(
            fact_id=grudge(npc),
            text=f"Who's {who}? Find out, and ask how they got on with Aris.",
        )
    return Lead(
        fact_id=grudge(npc),
        text=f"Who's {who}? {making.name(seen_by)} was at the maker space when someone rowed "
        f"with Aris. Ask {making.name(seen_by)} about it.",
    )


def _ask_about_night(making: _Building, heard_by: Id) -> Lead:
    return Lead(
        fact_id=SHOUTING,
        text=f"{making.name(heard_by)} was up late the night Aris was attacked. Ask whether "
        f"{making.name(heard_by)} heard anything.",
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


def _bystanders(npcs: list[Id], rng: random.Random) -> Iterator[Id]:
    """Residents to witness each part of the night, each once before anyone twice."""
    if not npcs:
        return
    while True:
        round_ = sorted(npcs)
        rng.shuffle(round_)
        yield from round_


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


async def make_incident(
    npcs: Sequence[Npc],
    now: datetime,
    llm: LLMClient | None,
    *,
    rng: random.Random | None = None,
    content: StoryContent | None = None,
    config: StoryConfig = DEFAULT_CONFIG,
) -> Made:
    """A new incident among `npcs`, with its motive written in one call, and their memories."""
    rng = rng or random.Random()
    content = content or load_story()
    found = attackers(npcs, content.grievances, rng, config)
    met = rng.choice(content.meeting_places)
    residents = [npc.name.split()[0] for npc in npcs]
    backstory, written = await write(llm, found, content, config, met=met, residents=residents)
    return build(npcs, found, backstory, now, rng, content, config, met=met, written=written)
