import random

from pydantic import Field

from simile.economy.config import EconomyConfig
from simile.schema import Id, Model, Timestamp


class Batch(Model):
    """A shop's meals for one shift: cooked when its keeper arrives, gone off at closing."""

    shop: Id
    shift: Timestamp = Field(description="When the shift it was cooked for starts.")
    cooked: int = Field(ge=0)
    left: int = Field(ge=0)
    sold_out: Timestamp | None = Field(default=None, description="When the last meal went.")
    gone_off: int = Field(default=0, ge=0, description="Meals left at closing.")


def stocked(home: Id, config: EconomyConfig) -> int:
    """A fridge nothing is known about: above `low`, the same for a home every time, and spread
    between homes so they don't all order on the same day."""
    return random.Random(home).randint(config.low + 1, config.fridge)
