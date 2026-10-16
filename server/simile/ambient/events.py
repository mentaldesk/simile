from dataclasses import dataclass

from simile.schema import Id
from simile.sim import Event


@dataclass(frozen=True)
class Nudged(Event):
    seeker: Id
    target: Id
