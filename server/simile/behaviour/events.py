from dataclasses import dataclass

from simile.schema import Id
from simile.sim import Event


@dataclass(frozen=True)
class GoalChosen(Event):
    npc: Id
    activity: str
    target: str | None
