from dataclasses import dataclass

from simile.schema import Id, Intention
from simile.sim import Event


@dataclass(frozen=True)
class GoalChosen(Event):
    npc: Id
    activity: str
    target: str | None


@dataclass(frozen=True)
class IntentionKept(Event):
    """They've started doing what they said: arrived, or begun talking to whom they meant to."""

    intention: Intention


@dataclass(frozen=True)
class IntentionBroken(Event):
    """It expired before they did it."""

    intention: Intention
