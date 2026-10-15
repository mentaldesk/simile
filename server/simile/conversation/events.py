from dataclasses import dataclass
from typing import Literal

from simile.schema import Id, Line
from simile.sim import Event

type Direction = Literal["down", "left", "right", "up"]


@dataclass(frozen=True)
class Facing(Event):
    """`entity` turned to face `toward`, who they're talking to."""

    entity: Id
    toward: Id
    direction: Direction


@dataclass(frozen=True)
class LineDrafted(Event):
    """Written ahead of its turn. `LineSpoken` follows with the same line at `line.timestamp`."""

    line: Line
