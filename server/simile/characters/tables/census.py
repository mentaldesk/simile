import random
from dataclasses import asdict, dataclass, fields

from simile.characters.tables.conditions import Context, Village, choose, fresh
from simile.characters.tables.load import Job, Tables, banded, load_tables

YEAR = 2026
RETIRED_FROM = 55
"""The age a retired resident's former job is drawn at, or theirs if they're younger."""


@dataclass(frozen=True)
class Skeleton:
    birth_year: int
    age: int
    gender: str
    origin: str
    given: str
    family: str
    born_here: bool
    arrived_at: int | None
    arrival: str | None
    background: str
    household: str
    upbringing: str
    siblings: int
    education: str
    partnership: str
    children: int
    health: str
    work: str
    occupation: str
    occupation_group: str | None

    @property
    def name(self) -> str:
        return f"{self.given} {self.family}"

    def facts(self) -> dict[str, object]:
        return asdict(self)


FIELDS = frozenset(f.name for f in fields(Skeleton))


def sample_skeleton(
    rng: random.Random,
    age: int,
    *,
    village: Village | None = None,
    tables: Tables | None = None,
    **fixed: object,
) -> Skeleton:
    """Draw every field not in `fixed`, each conditioned on those before it. A student's
    `education` is what they're studying for, and a fixed occupation means they work."""
    if unknown := set(fixed) - FIELDS:
        raise TypeError(f"not skeleton fields: {', '.join(sorted(unknown))}")
    t = tables or load_tables()
    census = t.census
    taken = village or Village()
    s: dict[str, object] = {"age": age, "birth_year": YEAR - age, **fixed}
    born = int(s["birth_year"])

    def unset(name: str) -> bool:
        return name not in s

    if unset("gender"):
        s["gender"] = choose(rng, list(census.gender), list(census.gender.values()))
    if unset("origin"):
        s["origin"] = choose(rng, [o.id for o in t.origins], [o.weight for o in t.origins])
    if (origin := t.origin.get(str(s["origin"]))) is None:
        raise ValueError(f"unknown origin '{s['origin']}': use origins_for(country) for its ids")
    if unset("given"):
        famous = {name.removesuffix(f" {s.get('family')}") for name in origin.famous}
        s["given"] = fresh(rng, origin.given_names(str(s["gender"]), born), taken.names | famous)
    if unset("family"):
        given = str(s["given"])
        s["family"] = fresh(rng, origin.surnames_for(given), taken.names | {given})
    if unset("born_here"):
        s["born_here"] = rng.random() < census.born_here
    if s["born_here"]:
        s.setdefault("arrival", None)
        s.setdefault("arrived_at", None)
    if unset("arrival"):
        arrivals = [a for a in census.arrival if a.ages[0] <= age]
        s["arrival"] = choose(rng, [a.id for a in arrivals], [a.weight for a in arrivals])
    if unset("arrived_at"):
        [arrival] = [a for a in census.arrival if a.id == s["arrival"]]
        s["arrived_at"] = rng.randint(arrival.ages[0], min(arrival.ages[1], age))
    if unset("background"):
        rows = census.background
        s["background"] = choose(rng, [r.id for r in rows], [banded(r.weight, born) for r in rows])
    if unset("upbringing"):
        rows = census.upbringing
        s["upbringing"] = choose(rng, [r.id for r in rows], [banded(r.weight, born) for r in rows])
    if unset("household"):
        [background] = [r for r in census.background if r.id == s["background"]]
        [upbringing] = [r for r in census.upbringing if r.id == s["upbringing"]]
        homes = [h for kind in upbringing.households for h in background.households.get(kind, [])]
        s["household"] = choose(rng, homes, [taken.damping(home) for home in homes]) or homes[0]
    if unset("siblings"):
        weights = banded(census.siblings, born)
        s["siblings"] = choose(rng, range(len(weights)), weights)
    if unset("education"):
        rows = census.education
        weights = [banded(r.weight, age) * r.background.get(str(s["background"]), 1) for r in rows]
        s["education"] = choose(rng, [r.id for r in rows], weights)
    if unset("partnership"):
        rows = census.partnership
        s["partnership"] = choose(rng, [r.id for r in rows], [banded(r.weight, age) for r in rows])
    if unset("children"):
        weights = list(banded(census.children, age))
        weights[0] *= census.childless.get(str(s["partnership"]), 1)
        s["children"] = choose(rng, range(len(weights)), weights)
    if unset("health"):
        s["health"] = _health(rng, t, age)
    if unset("work"):
        s["work"] = _work(rng, t, s)
    if unset("occupation"):
        s["occupation"], s["occupation_group"] = _occupation(rng, t, s, taken.jobs)
    if unset("occupation_group"):
        title = str(s["occupation"]).removeprefix("retired ")
        s["occupation_group"] = next((j.major for j in t.jobs if j.name == title), None)
    skeleton = Skeleton(**s)
    if village is not None:
        village.names.update((skeleton.given, skeleton.family))
        if skeleton.work in ("working", "retired", "student"):
            village.jobs.add(skeleton.occupation.removeprefix("retired "))
        village.drawn[skeleton.household] += 1
    return skeleton


def origins_for(country: str, *, tables: Tables | None = None) -> list[str]:
    """The origin ids for a country, such as a locked origin. India, for one, has several."""
    t = tables or load_tables()
    key = _country(country)
    if found := [origin.id for origin in t.origins if _country(origin.country) == key]:
        return found
    known = ", ".join(sorted({origin.country for origin in t.origins}))
    raise ValueError(f"no origins for country '{country}'; known countries: {known}")


def _country(name: str) -> str:
    return name.casefold().strip().removeprefix("the ")


def jobs_for(t: Tables, age: int, education: str) -> list[tuple[Job, float]]:
    """Every job someone of this age and education could hold, with its weight."""
    level = t.education[education]
    match = t.occupations.skill[education]
    return [
        (job, job.weight * match[job.skill - 1])
        for job in t.jobs
        if job.ages[0] <= age <= job.ages[1] and (level.degree or not job.degree)
    ]


def _health(rng: random.Random, t: Tables, age: int) -> str:
    health = t.census.health
    if rng.random() * 100 >= banded(health.share, age):
        return "none"
    rows = health.condition
    return choose(rng, [r.id for r in rows], [banded(r.weight, age) for r in rows]) or "none"


def _work(rng: random.Random, t: Tables, s: dict[str, object]) -> str:
    age = int(s["age"])
    occupation = s.get("occupation")
    if isinstance(occupation, str):
        return "retired" if occupation.startswith("retired ") else "working"
    if age < t.education[str(s["education"])].done_by:
        return "student"
    if rng.random() * 100 < banded(t.census.work.employed, age):
        return "working"
    context = Context(facts=s)
    rows = t.census.work.status
    weights = [banded(r.share, age) if context.allows(r.when) else 0 for r in rows]
    return choose(rng, [r.id for r in rows], weights) or "working"


def _occupation(
    rng: random.Random, t: Tables, s: dict[str, object], taken: set[str]
) -> tuple[str, str | None]:
    age, work, education = int(s["age"]), str(s["work"]), str(s["education"])
    if work in ("working", "retired"):
        options = jobs_for(t, min(age, RETIRED_FROM) if work == "retired" else age, education)
        unused = [(job, weight) for job, weight in options if job.name not in taken] or options
        job = choose(rng, [job for job, _ in unused], [weight for _, weight in unused])
        if job is not None:
            title = f"retired {job.name}" if work == "retired" else job.name
            return title, job.major
    if work == "student":
        [study] = [study for study in t.occupations.study if study.education == education]
        return fresh(rng, study.titles, taken), None
    [status] = [row for row in t.census.work.status if row.id == work] or [None]
    return (status.text if status else work), None
