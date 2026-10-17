import random
from collections.abc import Collection, Iterable, Sequence
from dataclasses import dataclass

from simile.npc.tables import ARRIVALS, EVENTS, NOT_WORKING, OCCUPATIONS, ORIGINS, STUDENTS

RETIREMENT_AGE = 66
RETIRED = 0.85
STUDENT_AGE = 22
STUDYING = 0.45
OUT_OF_WORK = 0.12
BORN_HERE = 0.2
MIN_EVENTS, MAX_EVENTS = 3, 6


@dataclass(frozen=True)
class Facts:
    """Who a resident is before Claude writes them, sampled in code from the tables."""

    name: str
    country: str
    arrived: tuple[int, str] | None
    occupation: str
    events: tuple[tuple[int, str], ...]

    @property
    def origin(self) -> str:
        if self.arrived is None:
            return f"born in the village to a family from {self.country}"
        age, why = self.arrived
        return f"born in {self.country}, came to the village at {age} {why}"


def sample_facts(people: Iterable[tuple[int, str]], rng: random.Random) -> list[Facts]:
    """Facts for each (age, gender), using no first name, surname or occupation twice."""
    names: set[str] = set()
    jobs: set[str] = set()
    cast = []
    for age, gender in people:
        origin = rng.choices(ORIGINS, [origin.weight for origin in ORIGINS])[0]
        first = _unused(origin.women if gender == "woman" else origin.men, rng, names)
        facts = Facts(
            name=f"{first} {_unused(origin.surnames, rng, names)}",
            country=origin.country,
            arrived=_arrival(age, rng),
            occupation=_occupation(age, rng, jobs),
            events=_events(age, rng),
        )
        names.update(facts.name.split())
        jobs.add(facts.occupation.removeprefix("retired "))
        cast.append(facts)
    return cast


def _unused(options: Sequence[str], rng: random.Random, taken: Collection[str]) -> str:
    return rng.choice([option for option in options if option not in taken] or options)


def _arrival(age: int, rng: random.Random) -> tuple[int, str] | None:
    if rng.random() < BORN_HERE:
        return None
    possible = [span for span in ARRIVALS if span.youngest <= age]
    arrival = rng.choices(possible, [span.weight for span in possible])[0]
    return rng.randint(arrival.youngest, min(arrival.oldest, age)), arrival.text


def _occupation(age: int, rng: random.Random, taken: Collection[str]) -> str:
    if age >= RETIREMENT_AGE and rng.random() < RETIRED:
        return f"retired {_job(age, rng, taken)}"
    if age <= STUDENT_AGE and rng.random() < STUDYING:
        return _unused(STUDENTS, rng, taken)
    if rng.random() < OUT_OF_WORK and (
        options := [span.text for span in NOT_WORKING if span.youngest <= age <= span.oldest]
    ):
        return _unused(options, rng, taken)
    return _job(age, rng, taken)


def _job(age: int, rng: random.Random, taken: Collection[str]) -> str:
    groups = [group for group in OCCUPATIONS if group.youngest <= age]
    group = rng.choices(groups, [group.weight for group in groups])[0]
    return _unused(group.titles, rng, taken)


def _events(age: int, rng: random.Random) -> tuple[tuple[int, str], ...]:
    possible = [event for event in EVENTS if event.youngest <= age]
    count = rng.randint(MIN_EVENTS, min(MAX_EVENTS, MIN_EVENTS + age // 20))
    chosen = rng.sample(possible, min(count, len(possible)))
    return tuple(sorted((rng.randint(e.youngest, min(e.oldest, age)), e.text) for e in chosen))
