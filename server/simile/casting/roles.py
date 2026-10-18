from collections.abc import Sequence

from simile.characters.jobs import job_of, retired
from simile.characters.tables import load_tables
from simile.characters.tables.load import Role
from simile.schema import Character, Id


def village_roles() -> list[Role]:
    """The village's own roles, from content/characters/tables/roles.toml, in casting order."""
    return list(load_tables().roles)


def fits(role: Role, character: Character) -> bool:
    """Whether their job fits the role. Nobody retired fits one."""
    job = job_of(character.occupation)
    return job is not None and not retired(character.occupation) and role.fits(job)


def holders(residents: Sequence[Character], roles: Sequence[Role]) -> dict[Id, Role]:
    """Who holds each role: in order, the first resident without one whose job fits it."""
    held: dict[Id, Role] = {}
    for role in roles:
        holder = next((c for c in residents if c.id not in held and fits(role, c)), None)
        if holder is not None:
            held[holder.id] = role
    return held
