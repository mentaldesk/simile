from pydantic import Field

from simile.schema import Item, Model


class SavedCreature(Model):
    """What a restart keeps of a creature that isn't as it started: README.md's *Saved*."""

    gone: bool = False
    """Destroyed, and it doesn't come back."""
    wounds: int = Field(default=0, ge=0)
    haul: list[Item] = []
    stocked: bool = False
    """It has had its starting haul, which a bot in a save from before them gets once."""
