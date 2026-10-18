from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass, fields
from statistics import mean, pstdev

from simile.casting.choose import elder, family
from simile.casting.model import Cast
from simile.casting.roles import holders, village_roles
from simile.characters.jobs import makes_or_studies
from simile.schema import Character, Id


@dataclass(frozen=True)
class Variety:
    """How varied a cast's jobs and ages are."""

    families: int
    """Distinct job families."""
    making: int
    """Residents who make or study something."""
    repeats: int
    """Residents outside the roles whose job family another of them already has."""
    elders: int
    """Residents over 60 with a trade from occupations.toml."""
    youngest: int
    oldest: int
    age_spread: float
    """The standard deviation of their ages."""


def variety(residents: Sequence[Character], year: int, roles: Collection[Id] = ()) -> Variety:
    """The variety of `residents` as of `year`, where those in `roles` hold the village's roles."""
    ages = [year - c.birth_year for c in residents]
    others = Counter(family(c) for c in residents if c.id not in roles)
    return Variety(
        families=len({family(c) for c in residents}),
        making=sum(makes_or_studies(c.occupation) for c in residents),
        repeats=sum(n - 1 for n in others.values()),
        elders=sum(elder(c, year) for c in residents),
        youngest=min(ages),
        oldest=max(ages),
        age_spread=pstdev(ages),
    )


def of_cast(made: Cast) -> Variety:
    residents = [r.character for r in made.residents]
    return variety(residents, made.game_date.year, set(holders(residents, village_roles())))


def average(varieties: Sequence[Variety]) -> dict[str, float]:
    names = [field.name for field in fields(Variety)]
    return {name: mean(getattr(v, name) for v in varieties) for name in names}
