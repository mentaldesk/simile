import tomllib
from collections import Counter
from collections.abc import Mapping
from functools import cache, cached_property
from pathlib import Path
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from simile.schema import CoreValue, Pay
from simile.schema.npc import Mannerism, Shifts

TABLES_DIR = Path(__file__).resolve().parents[4] / "content" / "characters" / "tables"

Id = Annotated[str, Field(pattern=r"^[a-z][a-z0-9_]*$", max_length=64)]
Text = Annotated[str, Field(min_length=1)]
Weight = Annotated[float, Field(gt=0)]
Share = Annotated[float, Field(ge=0)]
Percent = Annotated[float, Field(ge=0, le=100)]
Strength = Annotated[float, Field(ge=-3, le=3)]
Factor = Annotated[float, Field(gt=0, le=20)]
Age = Annotated[int, Field(ge=0, le=110)]


def _ordered(span: tuple[int, int]) -> tuple[int, int]:
    if span[0] > span[1]:
        raise ValueError(f"{span[0]} is after {span[1]}")
    return span


Span = Annotated[tuple[Age, Age], AfterValidator(_ordered)]
Years = Annotated[tuple[int, int], AfterValidator(_ordered)]
Banded = dict[int, Share]
"""Values keyed by the age (or birth year) each band starts at."""


class Table(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Between(Table):
    min: int | None = None
    max: int | None = None

    @model_validator(mode="after")
    def _bounded(self) -> "Between":
        if self.min is None and self.max is None:
            raise ValueError("give min, max or both")
        return self


class Except(Table):
    model_config = ConfigDict(extra="forbid", frozen=True, populate_by_name=True)

    excluded: list[str] = Field(alias="not", min_length=1)


Allowed = list[str] | bool | Between | Except


class Conditional(Table):
    """Conditions on a row, as content/characters/tables/README.md describes them."""

    when: dict[str, Allowed] = {}
    lean: dict[str, Strength] = {}
    boost: dict[str, Factor] = {}


class Origin(Table):
    id: Id
    country: Text
    accent: Text
    weight: Weight
    surnames: list[Text] = Field(min_length=8)
    women: dict[int, list[Text]]
    men: dict[int, list[Text]]
    famous: list[Text] = []
    """Full names of famous people the lists could otherwise make, which are never drawn."""

    def given_names(self, gender: str, birth_year: int) -> list[str]:
        if gender == "woman":
            return banded(self.women, birth_year)
        if gender == "man":
            return banded(self.men, birth_year)
        return banded(self.women, birth_year) + banded(self.men, birth_year)

    def surnames_for(self, given: str) -> list[str]:
        return [family for family in self.surnames if f"{given} {family}" not in self.famous]


class Arrival(Table):
    id: Id
    text: Text
    ages: Span
    weight: Weight = 1


class Background(Table):
    id: Id
    text: Text
    weight: Banded
    households: dict[Id, list[Text]]


class Category(Table):
    id: Id
    text: Text
    weight: Banded


class Upbringing(Category):
    households: list[Id] = Field(min_length=1)
    """The kinds of household in each background that fit this upbringing."""


class Education(Table):
    id: Id
    text: Text
    isced: Text
    degree: bool = False
    done_by: Age
    weight: Banded
    background: dict[str, Factor] = {}


class Condition(Table):
    id: Id
    text: Text
    weight: Banded


class Health(Table):
    share: dict[int, Percent]
    condition: list[Condition]


class Status(Conditional):
    id: Id
    text: Text
    share: Banded


class Work(Table):
    employed: dict[int, Percent]
    status: list[Status]


class Census(Table):
    gender: dict[str, Weight]
    born_here: Annotated[float, Field(ge=0, le=1)]
    arrival: list[Arrival]
    background: list[Background]
    upbringing: list[Upbringing]
    siblings: dict[int, list[Share]]
    education: list[Education]
    partnership: list[Category]
    children: dict[int, list[Share]]
    childless: dict[str, Factor]
    health: Health
    work: Work


class Title(Table):
    name: Text
    ages: Span | None = None
    degree: bool | None = None
    makes: bool | None = None


class Job(Table):
    name: str
    group: str
    """The ISCO-08 sub-major group's id, or the makers.toml family's."""
    major: str
    skill: int
    weight: float
    ages: tuple[int, int]
    degree: bool
    makes: bool
    """Whether whoever does it makes or studies something."""
    maker: bool = False
    """Whether it's from makers.toml."""


class Group(Table):
    id: Id
    isco: Text
    major: Id
    skill: Annotated[int, Field(ge=1, le=4)]
    employed: Weight
    ages: Span
    degree: bool = False
    makes: bool = False
    titles: list[Text | Title] = Field(min_length=1)

    def jobs(self) -> list[Job]:
        titles = [Title(name=t) if isinstance(t, str) else t for t in self.titles]
        return [
            Job(
                name=title.name,
                group=self.id,
                major=self.major,
                skill=self.skill,
                weight=self.employed / len(titles),
                ages=title.ages or self.ages,
                degree=self.degree if title.degree is None else title.degree,
                makes=self.makes if title.makes is None else title.makes,
            )
            for title in titles
        ]


class Study(Table):
    education: Id
    titles: list[Text] = Field(min_length=1)


class Occupations(Table):
    skill: dict[str, tuple[Factor, Factor, Factor, Factor]]
    group: list[Group]
    study: list[Study]


class Family(Table):
    id: Id
    name: Text
    major: Id
    skill: Annotated[int, Field(ge=1, le=4)]
    ages: Span
    degree: bool = False


class MakerJob(Table):
    title: Text
    family: Id
    ages: Span | None = None
    degree: bool | None = None


class Makers(Table):
    families: list[Family] = Field(min_length=1)
    jobs: list[MakerJob] = Field(min_length=1)

    def all(self) -> list[Job]:
        """Every job, each family's titles sharing a weight of 1."""
        families = {family.id: family for family in self.families}
        sizes = Counter(job.family for job in self.jobs)
        return [
            Job(
                name=job.title,
                group=family.id,
                major=family.major,
                skill=family.skill,
                weight=1 / sizes[family.id],
                ages=job.ages or family.ages,
                degree=family.degree if job.degree is None else job.degree,
                makes=True,
                maker=True,
            )
            for job in self.jobs
            if (family := families.get(job.family)) is not None
        ]


class Role(Table):
    """One of the village's own roles, as content/characters/tables/roles.toml describes it."""

    id: Id
    name: Text
    workplace: Id
    jobs: list[Text] = []
    families: list[Id] = []
    shifts: Shifts = Field(min_length=1)
    pay: Pay | None = None

    def fits(self, job: Job) -> bool:
        named = {title.casefold() for title in self.jobs}
        return job.name.casefold() in named or (job.maker and job.group in self.families)


class Event(Conditional):
    id: Id
    text: Text
    ages: Span
    years: Years | None = None
    weight: Weight = 1
    impact: Annotated[int, Field(ge=1, le=100)]
    valence: Annotated[float, Field(ge=-1, le=1)]
    rare: bool = False
    after: list[Id] = []
    not_with: list[Id] = []
    implied: dict[str, Allowed] = {}


class Contradiction(Conditional):
    id: Id
    value: CoreValue
    text: Text
    ages: Span = (16, 110)
    weight: Weight = 1


class Drawable(Conditional):
    """A tension row. `after` lists earlier draws, one of which must have happened."""

    id: Id
    weight: Weight = 1
    rare: bool = False
    after: list[Id] = []


class Wound(Drawable):
    text: Text


class Secret(Drawable):
    text: Text


class Want(Drawable):
    want: Text
    need: Text


class Tension(Table):
    contradiction: list[Contradiction]
    wound: list[Wound]
    secret: list[Secret]
    want: list[Want]


class Facet(Table):
    id: Id
    name: Text
    low: Text
    high: Text


class Domain(Table):
    id: Id
    name: Text
    values: dict[CoreValue, Strength]
    facet: list[Facet] = Field(min_length=1)


class Attachment(Conditional):
    id: Id
    name: Text
    text: Text
    weight: Weight


class Temperament(Table):
    domain: list[Domain]
    attachment: list[Attachment]


class MannerismGroup(Conditional):
    id: Id
    items: list[Mannerism] = Field(min_length=1)


class Mannerisms(Table):
    group: list[MannerismGroup]


class Tables(Table):
    origins: list[Origin]
    census: Census
    occupations: Occupations
    makers: Makers
    roles: list[Role]
    events: list[Event]
    tension: Tension
    temperament: Temperament
    mannerisms: Mannerisms

    @model_validator(mode="after")
    def _consistent(self) -> "Tables":
        from simile.characters.tables.check import problems

        if found := list(problems(self)):
            raise ValueError("\n".join(found))
        return self

    @cached_property
    def origin(self) -> Mapping[str, Origin]:
        return {origin.id: origin for origin in self.origins}

    @cached_property
    def event(self) -> Mapping[str, Event]:
        return {event.id: event for event in self.events}

    @cached_property
    def education(self) -> Mapping[str, Education]:
        return {education.id: education for education in self.census.education}

    @cached_property
    def jobs(self) -> list[Job]:
        """The jobs in occupations.toml."""
        return [job for group in self.occupations.group for job in group.jobs()]

    @cached_property
    def maker_jobs(self) -> list[Job]:
        return self.makers.all()

    @cached_property
    def titles(self) -> Mapping[str, Job]:
        """Every job in either table, by its title in lower case."""
        return {job.name.casefold(): job for job in [*self.jobs, *self.maker_jobs]}

    def job(self, title: str) -> Job | None:
        return self.titles.get(title.casefold())

    def role_jobs(self, role: Role) -> list[Job]:
        """The jobs that fit a role."""
        return [job for job in [*self.jobs, *self.maker_jobs] if role.fits(job)]


FILES = {
    "origins": ("names.toml", "origin"),
    "census": ("census.toml", None),
    "occupations": ("occupations.toml", None),
    "makers": ("makers.toml", None),
    "roles": ("roles.toml", "role"),
    "events": ("events.toml", "event"),
    "tension": ("tension.toml", None),
    "temperament": ("temperament.toml", None),
    "mannerisms": ("mannerisms.toml", None),
}


def read(directory: Path = TABLES_DIR) -> dict[str, object]:
    raw = {}
    for name, (file, key) in FILES.items():
        with (directory / file).open("rb") as f:
            data = tomllib.load(f)
        raw[name] = data[key] if key else data
    return raw


@cache
def load_tables(directory: Path = TABLES_DIR) -> Tables:
    """Every table, validated and cross-checked. Raises if any is malformed."""
    return Tables.model_validate(read(directory))


def banded[T](table: Mapping[int, T], key: int) -> T:
    starts = [start for start in table if start <= key]
    return table[max(starts) if starts else min(table)]
