from pydantic import Field

from simile.schema import Item, Model


class SavedCreature(Model):
    """What a restart keeps of a creature that isn't whole and empty-handed: README.md's *Saved*."""

    gone: bool = False
    """Destroyed, and it doesn't come back."""
    wounds: int = Field(default=0, ge=0)
    haul: list[Item] = []
