import logging
from collections.abc import Callable, Collection

from pydantic import BaseModel, ConfigDict, Field

from simile.player.pickups import Claim
from simile.player.where import here, location
from simile.schema import (
    HOLDS,
    Bionic,
    Id,
    Interactable,
    InteractableKind,
    Item,
    MapTile,
    Mind,
    Pile,
    Player,
)
from simile.world.movement import Movement, Point, cell_of, inside

logger = logging.getLogger(__name__)


class FindsConfig(BaseModel):
    """Where the player learns a recipe by being told it."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    told: dict[Id, Bionic] = Field(
        default={"clinic": Bionic.POWER_CELL},
        description="The recipe each place's keeper tells them on walking in, by location id: the "
        "doctor tells them the power cell's, since nothing she fits runs without one.",
    )


DEFAULT_CONFIG = FindsConfig()


class Finds:
    """Searching furniture, dead appliances and jacks once for what they hold, and learning the
    recipes they teach or a keeper tells."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        known: Callable[[], Collection[Bionic]],
        config: FindsConfig = DEFAULT_CONFIG,
    ) -> None:
        self.player = player
        self.movement = movement
        self.known = known
        self.config = config

    def claim(self, at: Point) -> Claim | None:
        """Searching the unsearched thing they stand at, before any pile or clue."""
        thing = self.thing(at)
        return None if thing is None else Claim(-1.0, lambda: self.search(thing, at))

    def thing(self, at: Point) -> Interactable | None:
        """What there is to search at `at`: a searchable, or a jack holding something while the
        datajack is in."""
        town = self.movement.maps.get(at.map)
        cell = cell_of(at)
        for thing in town.interactables if town is not None else ():
            if thing.kind not in HOLDS or thing.id in self.player.searched:
                continue
            if thing.kind is InteractableKind.JACK and not self._jacked(thing):
                continue
            if any((tile.x, tile.y) == cell for tile in thing.stand):
                return thing
        return None

    def search(self, thing: Interactable, at: Point) -> None:
        if thing.teaches is not None:
            self.learn(thing.teaches)
        room = self.player.carry_limit - self.player.load
        taken: list[Item] = []
        kept: list[Item] = []
        for item in thing.items:
            if item.weight <= room + 1e-9:
                taken.append(item)
                room -= item.weight
            else:
                kept.append(item)
        if kept:
            x, y = cell_of(at)
            self.player.left = [
                *self.player.left,
                Pile(at=MapTile(map=at.map, x=x, y=y), items=kept),
            ]
        self.player.items = [*self.player.items, *taken]
        self.player.searched = [*self.player.searched, thing.id]
        logger.info("The player searches %s", thing.label)

    def learn(self, bionic: Bionic) -> bool:
        """Adds `bionic`'s recipe to their mind, if it's new to them. Whether they learned it."""
        mind = self.player.mind
        if bionic in mind.recipes:
            return False
        if bionic not in self.known():
            logger.warning("There's no recipe for %s to learn", bionic)
            return False
        self.player.mind = Mind(recipes=[*mind.recipes, bionic], sold=mind.sold)
        logger.info("The player learns the recipe for %s", bionic)
        return True

    def tick(self, dt: float) -> None:
        """Teaches them what the keeper where they stand tells them."""
        at = here(self.movement)
        if at is None:
            return
        for place, bionic in self.config.told.items():
            if bionic not in self.player.mind.recipes:
                found = location(self.movement, place)
                if found is not None and inside(found, at):
                    self.learn(bionic)

    def _jacked(self, jack: Interactable) -> bool:
        working = Bionic.DATAJACK in self.player.body.bionics
        return working and (bool(jack.items) or jack.teaches is not None)
