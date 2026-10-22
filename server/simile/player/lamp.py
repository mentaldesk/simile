import logging
from collections.abc import Callable

from pydantic import BaseModel, ConfigDict, Field

from simile.schema import PLAYER_ID, Interactable, InteractableKind, Item, ItemKind, Player
from simile.sim import Clock
from simile.world.movement import Movement, cell_of

logger = logging.getLogger(__name__)

HOUR = 3600.0


class LampConfig(BaseModel):
    """How fast the lamp's battery runs down and charges."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    drain: float = Field(
        default=3.0,
        gt=0,
        description="How much of a full battery it uses each sim hour it's on: twenty minutes.",
    )
    charge: float = Field(
        default=60.0,
        gt=0,
        description="How much a plug charges it each sim hour: from flat to full in a minute.",
    )


DEFAULT_LAMP = LampConfig()


class Lamp:
    """The player's lamp: drains while on, charges at a plug, and goes out when flat."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        clock: Clock,
        *,
        playing: Callable[[], bool] = lambda: True,
        config: LampConfig = DEFAULT_LAMP,
    ) -> None:
        self.player = player
        self.movement = movement
        self.clock = clock
        self.playing = playing
        self.config = config

    def tick(self, dt: float) -> None:
        index = self._index()
        if index is None or not self.playing():
            return
        lamp = self.player.items[index]
        charge, on = lamp.charge or 0.0, bool(lamp.on)
        if self.plug() is not None:
            charge = min(charge + self.config.charge * dt / HOUR, 1.0)
        elif on:
            charge = max(charge - self.config.drain * dt / HOUR, 0.0)
            on = charge > 0
            if not on:
                logger.info("%s  The player's lamp runs flat and goes out", self.clock)
        if (charge, on) != (lamp.charge, lamp.on):
            self._replace(index, lamp.model_copy(update={"charge": charge, "on": on}))

    def switch(self, on: bool) -> bool:
        """Switches the lamp they carry on or off. Whether it changed: a flat one stays off."""
        index = self._index()
        if index is None:
            return False
        lamp = self.player.items[index]
        if lamp.on == on or (on and not lamp.charge):
            return False
        self._replace(index, lamp.model_copy(update={"on": on}))
        return True

    def plug(self) -> Interactable | None:
        """The plug the player stands at: they're on one of its stand tiles."""
        here = self.movement.entities().get(PLAYER_ID)
        if here is None or (town := self.movement.maps.get(here.map)) is None:
            return None
        x, y = cell_of(here)
        return next(
            (
                item
                for item in town.interactables
                if item.kind is InteractableKind.PLUG
                and any((tile.x, tile.y) == (x, y) for tile in item.stand)
            ),
            None,
        )

    def _index(self) -> int | None:
        kinds = (item.kind for item in self.player.items)
        return next((i for i, kind in enumerate(kinds) if kind is ItemKind.LAMP), None)

    def _replace(self, index: int, lamp: Item) -> None:
        items = self.player.items
        self.player.items = [*items[:index], lamp, *items[index + 1 :]]
