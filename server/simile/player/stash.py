import math
from collections.abc import Sequence
from typing import Final, Literal

from simile.player.pickups import joined
from simile.player.where import here
from simile.schema import Id, Item, ItemKind, Player
from simile.world.movement import Movement, cell_of

LOCKERS: Final = "lockers"
SLACK: Final = 1e-9
"""Kilos a load may be over by, as `Pickups.pick_up` allows, so `0.3 / 0.1` is 3 and not 2.99..."""
FINEST: Final = 1_000_000
"""Material splits to a millionth, and a remainder smaller than that moves with the rest."""


def fitting(item: Item, room: float) -> float:
    """How much of the stack fits in `room` kg: rounds whole, material in any amount, and anything
    else all or none. What weighs nothing always fits."""
    if item.weight == 0 or item.load <= room + SLACK:
        return item.amount
    fits = (room + SLACK) / item.weight
    if item.kind is ItemKind.ROUNDS:
        return float(max(math.floor(fits), 0))
    if item.kind is not ItemKind.MATERIAL:
        return 0.0
    part = max(math.floor(fits * FINEST) / FINEST, 0.0)
    return item.amount if part > 0 and item.amount - part < 1 / FINEST else part


def split(items: Sequence[Item], id: Id, room: float) -> tuple[Item, list[Item]] | None:
    """What of the first of `id` fits in `room` kg, and `items` with the rest left in its place."""
    at = next((i for i, item in enumerate(items) if item.id == id), None)
    if at is None:
        return None
    item = items[at]
    part = fitting(item, room)
    if part <= 0:
        return None
    rest = item.amount - part
    kept = [item.model_copy(update={"amount": rest})] if rest > 0 else []
    return item.model_copy(update={"amount": part}), [*items[:at], *kept, *items[at + 1 :]]


class Lockers:
    """Aris's lockers, where the player moves things between what they carry and their stash."""

    def __init__(self, player: Player, movement: Movement) -> None:
        self.player = player
        self.movement = movement

    def move(self, item: Id, action: Literal["store", "take"]) -> bool:
        """Moves as much of the first of `item` as fits, where they stand at the lockers. Whether
        any moved. A lamp stored goes off."""
        if not self._at():
            return False
        player, stash = self.player, self.player.stash
        if action == "take":
            taken = split(stash.items, item, player.carry_limit - player.load)
            if taken is None:
                return False
            player.stash = stash.model_copy(update={"items": taken[1]})
            player.items = joined(player.items, [taken[0]])
            return True
        stored = split(player.items, item, stash.limit - stash.load)
        if stored is None:
            return False
        moved = stored[0]
        if moved.kind is ItemKind.LAMP:
            moved = moved.model_copy(update={"on": False})
        player.items = stored[1]
        player.stash = stash.model_copy(update={"items": joined(stash.items, [moved])})
        return True

    def _at(self) -> bool:
        at = here(self.movement)
        town = self.movement.maps.get(at.map) if at is not None else None
        if at is None or town is None:
            return False
        lockers = (item for item in town.interactables if item.id == LOCKERS)
        return any((tile.x, tile.y) == cell_of(at) for item in lockers for tile in item.stand)
