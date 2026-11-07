import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from pydantic import BaseModel, ConfigDict, Field

from simile.behaviour import Activity, Goal, Need
from simile.economy import PLAYER
from simile.player.config import DEFAULT_CONFIG, PlayerConfig
from simile.player.hours import hours, next_opening
from simile.player.power import cell_in
from simile.player.where import here, location
from simile.protocol import Meal, Shut, ShutReason
from simile.schema import Id, ItemKind, Location, Player
from simile.sim import Clock
from simile.world.movement import Movement, Point, inside

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)

HOUR = 3600.0
HOME = "home"

type Supply = Callable[[Goal, Need], float]


class StarvingConfig(BaseModel):
    """What going without food does once hunger is full."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    every: float = Field(
        default=0.2, gt=0, description="Sim hours between each pang: twelve sim minutes."
    )
    damage: float = Field(
        default=0.1,
        gt=0,
        le=1,
        description="The health each pang takes: from full to dead in ten pangs, two sim hours, "
        "and a hit the client shows at full strength.",
    )


DEFAULT_STARVING = StarvingConfig()


class Hunger:
    """The player's hunger, eating and starving, until a power cell takes the stomach's place.
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
        pang: Callable[[float], None] = lambda damage: None,
        config: PlayerConfig = DEFAULT_CONFIG,
        starving: StarvingConfig = DEFAULT_STARVING,
    ) -> None:
        self.player = player
        self.movement = movement
        self.clock = clock
        self.supply = supply
        """B1's supply hook: whether a shop would feed a resident now."""
        self.economy = economy
        """Its `player` is this one, so meals are paid through its ledger."""
        self.playing = playing
        self.pang = pang
        """Takes that much of their health, starving them to death at none."""
        self.config = config
        self.starving = starving
        self.since_pang = 0.0

    def tick(self, dt: float) -> None:
        if self._on_cell():
            self.player.hunger = 0.0
            return
        if not self.playing():
            return
        hunger = self.player.hunger + self.config.rise * dt / HOUR
        self.player.hunger = min(hunger, 1.0)
        if hunger < 1:
            self.since_pang = 0.0
            return
        self.since_pang += dt
        every = self.starving.every * HOUR
        while self.since_pang >= every and self.player.hunger >= 1:
            self.since_pang -= every
            self.pang(self.starving.damage)

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
