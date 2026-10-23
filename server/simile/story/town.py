import random
import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum

from simile.schema import CoreValue, Fact, Id, Lead, Npc

PREFIX = "town_"
"""Every town fact's id starts with it, so none is ever one of the incident's."""
SETTLED_YEARS = 15
"""Years in the village after which a resident knows it as well as anyone."""
GROWN_UP = 18
"""Nobody has lived here longer than they've been an adult."""
AFFINITY = 0.3
"""How much more likely a fact is to someone whose job, interests or street touch it."""

V = CoreValue
CURIOUS = {V.ADVENTURE: 0.4, V.OPEN_MINDEDNESS: 0.2, V.CONNECTION: 0.2, V.SECURITY: -0.2}
SOCIABLE = {V.CONNECTION: 0.2}


class Knowing(StrEnum):
    """How a resident knows a town fact: for certain, or only as a rumour."""

    KNOWS = "knows"
    HEARD = "heard"


@dataclass(frozen=True)
class TownFact:
    """Something about the village, and how likely a resident is to know it."""

    id: Id
    where: str
    what: str
    rumour: str
    unknown: str
    """What they don't know, said as "You don't know..." when they don't."""
    knows: float
    heard: float = 0.0
    """The chance on top of `knows` they've only heard it as a rumour."""
    tenure: float = 0.0
    """How much likelier an old hand is to know it than a newcomer."""
    values: Mapping[CoreValue, float] = field(default_factory=dict)
    words: tuple[str, ...] = ()
    """Parts of words in their job or interests that make them likelier to know it."""
    near: tuple[Id, ...] = ()
    """Homes or workplaces that make them likelier to know it."""
    at: tuple[Id, ...] = ()
    """Homes or workplaces whose residents know it for certain."""
    journal: bool = False
    leads: tuple[Lead, ...] = ()

    def said(self, knowing: Knowing) -> str:
        return self.what if knowing is Knowing.KNOWS else self.rumour

    def fact(self, knowing: Knowing, when: datetime) -> Fact:
        """As one of S2's facts, for the journal."""
        return Fact(
            id=self.id,
            what=self.said(knowing),
            when=when,
            where=self.where,
            about=[],
            known_by=[],
            leads=list(self.leads),
        )


@dataclass(frozen=True)
class Place:
    """Somewhere the player can ask about, and the facts a resident draws on to answer."""

    name: str
    pattern: re.Pattern[str]
    facts: tuple[Id, ...]


def _amenity(id: Id, where: str, what: str, unknown: str, *at: Id) -> TownFact:
    return TownFact(id, where, what, what, unknown, 0.9, 0.05, 0.2, SOCIABLE, at=(where, *at))


WAY_DOWN_LEAD = "There's an old metro under the village. Ask around for the way down."
BANYAN_ROW = ("house_8", "house_9", "house_10", "gallery")

FACTS = {
    fact.id: fact
    for fact in [
        _amenity(
            "town_cafe",
            "coffee_shop",
            "The Daily Grind is the café on High Street, just west of the square: coffee at the "
            "counter downstairs, tables upstairs and a terrace out front.",
            "You don't know the café.",
        ),
        _amenity(
            "town_noodle_bar",
            "noodle_bar",
            "Golden Bowl Noodles is the noodle bar at the east end of High Street, past the "
            "square.",
            "You don't know the noodle bar.",
        ),
        _amenity(
            "town_maker_space",
            "maker_space",
            "Spark Maker Space, at the west end of High Street, is a workshop with tools and "
            "machines anyone can use to make and mend things.",
            "You don't know the maker space.",
        ),
        _amenity(
            "town_gallery",
            "gallery",
            "The Gallery, on Banyan Row, shows local artists' paintings.",
            "You don't know the gallery.",
        ),
        _amenity(
            "town_terminals",
            "square",
            "News terminals for the village news stand on the square, at the park gate on Lychee "
            "Lane, and by the river at the end of Banyan Row.",
            "You don't know where the news terminals are.",
        ),
        _amenity(
            "town_park",
            "park",
            "Lotus Lake Park is at the east end of Lychee Lane, with benches, trees and a lookout "
            "up a ladder.",
            "You don't know the park.",
        ),
        _amenity(
            "town_square",
            "square",
            "The Town Square, with its fountain and benches, is in the middle of High Street. "
            "Kapok Walk and Lychee Lane lead off it, and steps at its east end go down to "
            "Banyan Row.",
            "You don't know the square.",
        ),
        _amenity(
            "town_promenade",
            "banyan_row",
            "Past the Gallery, Banyan Row's east end goes down steps to the river promenade, "
            "with benches and a news terminal.",
            "You don't know the river promenade.",
            *BANYAN_ROW,
        ),
        TownFact(
            "town_metro",
            "metro",
            "There's an old metro station under the river promenade, shut for years.",
            "People say there's an old metro station somewhere under the village, shut for years.",
            "You've never heard of an old metro under the village.",
            knows=0.45,
            heard=0.2,
            tenure=0.5,
            values=SOCIABLE,
            words=("river", "ferry", "train", "salvage", "histor"),
            near=BANYAN_ROW,
            journal=True,
            leads=(Lead(fact_id="town_way_down", text=WAY_DOWN_LEAD),),
        ),
        TownFact(
            "town_way_down",
            "banyan_row",
            "A stairway down to the old metro starts on the river promenade at the east end of "
            "Banyan Row, just past the news terminal.",
            "Supposedly there's a way down to the old metro somewhere on the river promenade.",
            "You don't know of any way down to the old metro.",
            knows=0.0,
            heard=0.12,
            tenure=0.2,
            values=CURIOUS,
            words=("river", "ferry", "salvage", "scrap", "trek", "trail", "explor", "night"),
            near=BANYAN_ROW,
            journal=True,
        ),
        TownFact(
            "town_clinic",
            "clinic",
            "Someone runs a clinic down in the old metro, off the books, fitting bionics.",
            "There's talk of a back-street clinic down in the old metro that fits bionics.",
            "You've never heard of a clinic down there.",
            knows=-0.05,
            heard=0.12,
            tenure=0.1,
            values=CURIOUS,
            words=("bionic", "implant", "electronic", "medic", "nurse", "health", "struggling"),
            journal=True,
        ),
        TownFact(
            "town_scrap_trader",
            "scrap_stall",
            "A scrap trader keeps a stall on the old metro's platform and buys salvage.",
            "Word is a scrap trader down in the old metro buys salvage, no questions asked.",
            "You've never heard of a scrap trader down there.",
            knows=-0.03,
            heard=0.12,
            tenure=0.1,
            values=CURIOUS,
            words=("salvage", "scrap", "repair", "reuse", "upcycl", "tool"),
            near=("maker_space",),
            journal=True,
        ),
    ]
}
METRO_DETAILS = ("town_way_down", "town_clinic", "town_scrap_trader")


def _place(name: str, words: str, *facts: Id) -> Place:
    return Place(name, re.compile(rf"\b(?:{words})\b", re.IGNORECASE), facts)


METRO = ("town_metro", "town_way_down", "town_clinic", "town_scrap_trader")
PLACES = [
    _place(
        "the old metro",
        r"metro|subway|underground|tube|stations?|trains?|way down|stair(?:way|s) down",
        *METRO,
    ),
    _place("the clinic", r"clinic|doctors?|surgeon|bionics?|implants?", *METRO),
    _place("the scrap trader", r"scrap|salvage|junk|scrap ?trader", *METRO),
    _place("the café", r"caf[eé]s?|coffee|daily grind|barista|espresso", "town_cafe"),
    _place("the noodle bar", r"noodles?|noodle bar|golden bowl|ramen", "town_noodle_bar"),
    _place("the maker space", r"maker ?space|spark|workshop", "town_maker_space"),
    _place("the gallery", r"galler(?:y|ies)|exhibitions?", "town_gallery"),
    _place("the news terminals", r"terminals?", "town_terminals"),
    _place("the park", r"park|lotus lake|lake|lookout", "town_park"),
    _place("the square", r"square|fountain", "town_square"),
    _place(
        "the river promenade",
        r"river|promenade|riverside|banyan row",
        "town_promenade",
    ),
]


def asked_about(said: str) -> list[Place]:
    """The places `said` asks about, in `PLACES` order."""
    return [place for place in PLACES if place.pattern.search(said)]


def settled(npc: Npc, rng: random.Random) -> float:
    """How long they've lived here, from 0 for a newcomer to 1 for an old hand, drawn by age."""
    years = rng.uniform(0, max(1, npc.age - GROWN_UP))
    return min(1.0, years / SETTLED_YEARS)


def _shift(fact: TownFact, npc: Npc, tenure: float) -> float:
    about = " ".join([npc.occupation, *npc.interests]).lower()
    close = any(word in about for word in fact.words) or bool(
        {npc.home, npc.workplace} & set(fact.near)
    )
    values = sum(weight * (npc.values[value] - 0.5) for value, weight in fact.values.items())
    return fact.tenure * (tenure - 0.5) + values + AFFINITY * close


def world_seed() -> int:
    """The cast's seed, or 0 for the village in content/."""
    from simile.casting.store import load_cast

    cast = load_cast()
    return cast.seed if cast is not None else 0


def known(npc: Npc, seed: int) -> dict[Id, Knowing]:
    """What `npc` knows of the town, the same for the same world's seed and resident."""
    rng = random.Random(f"town/{seed}/{npc.id}")
    tenure = settled(npc, rng)
    knowing: dict[Id, Knowing] = {}
    for fact in FACTS.values():
        roll, shift = rng.random(), _shift(fact, npc, tenure)
        if {npc.home, npc.workplace} & set(fact.at) or roll < fact.knows + shift:
            knowing[fact.id] = Knowing.KNOWS
        elif roll < fact.knows + fact.heard + shift:
            knowing[fact.id] = Knowing.HEARD
    details = [knowing[id] for id in METRO_DETAILS if id in knowing]
    if details and knowing.get("town_metro") is not Knowing.KNOWS:
        knowing["town_metro"] = min(details, key=list(Knowing).index)
    return knowing
