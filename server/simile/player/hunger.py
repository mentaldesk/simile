import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from simile.behaviour import Activity, Goal, Need
from simile.economy import PLAYER
from simile.player.config import DEFAULT_CONFIG, PlayerConfig
from simile.player.hours import hours, next_opening
from simile.player.power import cell_in
from simile.player.where import here, location
from simile.protocol import Meal, Shut, ShutReason, Vital
from simile.schema import PLAYER_ID, Id, ItemKind, Location, MapTile, Pile, Player
from simile.sim import Clock
from simile.world.movement import Movement, Point, cell_of, inside

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)

HOUR = 3600.0
HOME = "home"

type Supply = Callable[[Goal, Need], float]


class Hunger:
    """The player's hunger, eating and collapsing, until a power cell takes the stomach's place.
    Tick it on the sim loop."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        clock: Clock,
        *,
        supply: Supply = lambda goal, need: 1.0,
        economy: "Economy | None" = None,
        playing: Callable[[], bool] = lambda: True,
        collapsed: Callable[[MapTile, Vital], None] = lambda home, cause: None,
        config: PlayerConfig = DEFAULT_CONFIG,
    ) -> None:
        self.player = player
        self.movement = movement
        self.clock = clock
        self.supply = supply
        """B1's supply hook: whether a shop would feed a resident now."""
        self.economy = economy
        """Its `player` is this one, so meals are paid through its ledger."""
        self.playing = playing
        self.collapsed = collapsed
        """Told where they wake after collapsing, and what ran out."""
        self.config = config

    def tick(self, dt: float) -> None:
        if self._on_cell():
            self.player.hunger = 0.0
            return
        if not self.playing():
            return
        hunger = self.player.hunger + self.config.rise * dt / HOUR
        if hunger >= 1:
            self.collapse()
        else:
            self.player.hunger = hunger

    def meal(self) -> Meal | None:
        """The meal on offer where they stand, if any."""
        at = here(self.movement)
        if at is None or self._on_cell():
            return None
        home = location(self.movement, self.config.home)
        if home is not None and inside(home, at):
            return Meal(place=home.id, name=HOME, price=0)
        found = self._shop(at)
        if found is None or not self._serving(found[0].id):
            return None
        shop, price = found
        return Meal(place=shop.id, name=shop.name, price=price)

    def shut(self) -> Shut | None:
        """The shop where they stand, if it sells meals but isn't serving them, and when it next
        does."""
        at = here(self.movement)
        found = None if at is None or self._on_cell() else self._shop(at)
        if found is None or self._serving(found[0].id):
            return None
        shop, _ = found
        reason = ShutReason.SOLD_OUT if self._sold_out(shop.id) else ShutReason.CLOSED
        npcs = self.economy.behaviour.npcs.values() if self.economy is not None else []
        opens = next_opening(hours(shop.id, npcs), self.clock.now)
        return Shut(place=shop.id, name=shop.name, reason=reason, opens=opens)

    def eat(self, item: Id | None) -> bool:
        """Eats a carried food item by id, or with None the meal on offer. Whether they ate: never
        on a power cell."""
        if self._on_cell():
            return False
        return self._eat_meal() if item is None else self._eat_item(item)

    def collapse(self, cause: Vital = Vital.HUNGER) -> None:
        """Leaves all but the lamp where they are, and wakes them at home, still hungry if that's
        why."""
        at = here(self.movement)
        kept = [item for item in self.player.items if item.kind is ItemKind.LAMP]
        dropped = [item for item in self.player.items if item.kind is not ItemKind.LAMP]
        if at is not None and dropped:
            pile = Pile(at=ground(self.movement, at), items=dropped)
            self.player.left = [*self.player.left, pile]
            self.player.items = kept
        house = self.movement.town.location(self.config.home)
        home = MapTile(map=house.map, x=house.entry.x, y=house.entry.y)
        self.movement.track(PLAYER_ID, Point(home.x, home.y, home.map))
        if cause is Vital.HUNGER:
            self.player.hunger = self.config.waking
        logger.info("%s  The player collapses (%s) and wakes at home", self.clock, cause)
        self.collapsed(home, cause)

    def _on_cell(self) -> bool:
        return cell_in(self.player.body) is not None

    def _eat_meal(self) -> bool:
        meal = self.meal()
        if meal is None or meal.price > self.player.money:
            return False
        if meal.place == self.config.home:
            relief = self.config.home_meal
        else:
            self._pay(meal)
            relief = self.config.meals[meal.place]
        self._relieve(relief)
        logger.info("%s  The player eats at %s", self.clock, meal.name)
        return True

    def _eat_item(self, id: Id) -> bool:
        items = self.player.items
        found = (i for i, item in enumerate(items) if item.id == id and item.kind is ItemKind.FOOD)
        index = next(found, None)
        if index is None:
            return False
        self.player.items = items[:index] + items[index + 1 :]
        self._relieve(self.config.food)
        return True

    def _pay(self, meal: Meal) -> None:
        """Pays the keeper through the ledger and takes one from the batch."""
        assert self.economy is not None
        self.economy.buy(PLAYER, meal.place, meal.price)
        shop, batch = self.economy.config.shops[meal.place], self.economy.batches.get(meal.place)
        if shop.batch is not None and batch is not None and batch.left > 0:
            batch.left -= 1
            if batch.left == 0:
                batch.sold_out = self.clock.now

    def _relieve(self, amount: float) -> None:
        self.player.hunger = max(self.player.hunger - amount, 0.0)

    def _serving(self, place: Id) -> bool:
        try:
            activity = Activity(place)
        except ValueError:
            return False
        return self.supply(Goal(activity, place), Need.HUNGER) > 0

    def _shop(self, at: Point) -> tuple[Location, float] | None:
        """The shop that sells meals where they stand, with a meal's price there."""
        for place in self.config.meals:
            shop, price = location(self.movement, place), self._price(place)
            if shop is not None and price is not None and inside(shop, at):
                return shop, price
        return None

    def _sold_out(self, place: Id) -> bool:
        """For a shop that isn't serving: its keeper is in, so its batch has gone."""
        economy = self.economy
        return (
            economy is not None
            and economy.config.shops[place].batch is not None
            and economy.staffed(place)
        )

    def _price(self, place: Id) -> float | None:
        shop = self.economy.config.shops.get(place) if self.economy is not None else None
        return None if shop is None else shop.meal


def ground(movement: Movement, here: Point) -> MapTile:
    """The cell they're on, or the first one below it to stand on."""
    x, y = (max(n, 0) for n in cell_of(here))
    town = movement.maps.get(here.map)
    if town is not None:
        x, y = min(x, town.width - 1), min(y, town.height - 1)
        y = next((row for row in range(y, town.height) if town.standing(x, row)), y)
    return MapTile(map=here.map, x=x, y=y)
