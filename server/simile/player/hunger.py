import logging
import math
from collections.abc import Callable
from typing import TYPE_CHECKING

from simile.behaviour import Activity, Goal, Need
from simile.economy import OUTSIDE
from simile.player.config import DEFAULT_CONFIG, PlayerConfig
from simile.protocol import Meal
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
    """The player's hunger. It rises while someone's playing, a meal or food they carry relieves
    it, and at 1 they collapse: they wake at home, still hungry, with what they carried left where
    they fell, for them to go back for. Tick it on the sim loop."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        clock: Clock,
        *,
        supply: Supply = lambda goal, need: 1.0,
        economy: "Economy | None" = None,
        playing: Callable[[], bool] = lambda: True,
        collapsed: Callable[[MapTile], None] = lambda home: None,
        config: PlayerConfig = DEFAULT_CONFIG,
    ) -> None:
        self.player = player
        self.movement = movement
        self.clock = clock
        self.supply = supply
        """B1's supply hook: whether a shop would feed a resident now."""
        self.economy = economy
        self.playing = playing
        self.collapsed = collapsed
        """Told where they wake after collapsing."""
        self.config = config

    def tick(self, dt: float) -> None:
        if not self.playing():
            return
        hunger = self.player.hunger + self.config.rise * dt / HOUR
        if hunger >= 1:
            self.collapse()
        else:
            self.player.hunger = hunger

    def meal(self) -> Meal | None:
        """The meal on offer where they stand: at home for nothing, or at a shop that's serving,
        at its meal price."""
        here = self._here()
        if here is None:
            return None
        home = self._location(self.config.home)
        if home is not None and inside(home, here):
            return Meal(place=home.id, name=HOME, price=0)
        for place in self.config.meals:
            shop, price = self._location(place), self._price(place)
            if shop is None or price is None or not inside(shop, here):
                continue
            return Meal(place=place, name=shop.name, price=price) if self._serving(place) else None
        return None

    def eat(self, item: Id | None) -> bool:
        """Eats a food item they carry, by its id, or with None the meal on offer where they
        stand, paying for it. Whether they ate."""
        return self._eat_meal() if item is None else self._eat_item(item)

    def collapse(self) -> None:
        """Leaves what they carry where they are, but for the lamp, and puts them at home, still
        hungry."""
        here = self._here()
        kept = [item for item in self.player.items if item.kind is ItemKind.LAMP]
        dropped = [item for item in self.player.items if item.kind is not ItemKind.LAMP]
        if here is not None and dropped:
            pile = Pile(at=ground(self.movement, here), items=dropped)
            self.player.left = [*self.player.left, pile]
            self.player.items = kept
        location = self.movement.town.location(self.config.home)
        home = MapTile(map=location.map, x=location.entry.x, y=location.entry.y)
        self.movement.track(PLAYER_ID, Point(home.x, home.y, home.map))
        self.player.hunger = self.config.waking
        logger.info("%s  The player collapses from hunger and wakes at home", self.clock)
        self.collapsed(home)

    def pick_up(self) -> bool:
        """Picks up, from the nearest pile they left within reach, each item that still fits under
        their carry limit, in order. Whether they picked anything up."""
        here = self._here()
        if here is None:
            return False
        near = [
            (distance, index)
            for index, pile in enumerate(self.player.left)
            if pile.at.map == here.map
            and (distance := math.dist(here, (pile.at.x, pile.at.y))) <= self.config.reach
        ]
        if not near:
            return False
        _, index = min(near)
        pile, room = self.player.left[index], self.player.carry_limit - self.player.load
        taken, kept = [], []
        for item in pile.items:
            if item.weight <= room + 1e-9:
                taken.append(item)
                room -= item.weight
            else:
                kept.append(item)
        if not taken:
            return False
        left = list(self.player.left)
        if kept:
            left[index] = Pile(at=pile.at, items=kept)
        else:
            del left[index]
        self.player.items = [*self.player.items, *taken]
        self.player.left = left
        return True

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
        """To the shop's keeper through the ledger, as from outside the village, and from its
        batch."""
        assert self.economy is not None
        self.player.money = max(self.player.money - meal.price, 0.0)
        self.economy.buy(OUTSIDE, meal.place, meal.price)
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

    def _price(self, place: Id) -> float | None:
        shop = self.economy.config.shops.get(place) if self.economy is not None else None
        return None if shop is None else shop.meal

    def _location(self, place: Id) -> Location | None:
        try:
            return self.movement.town.location(place)
        except KeyError:
            return None

    def _here(self) -> Point | None:
        return self.movement.entities().get(PLAYER_ID)


def ground(movement: Movement, here: Point) -> MapTile:
    """The cell they're on, or if that's mid-air or partway up stairs or a ladder, the first one
    below it to stand on."""
    x, y = (max(n, 0) for n in cell_of(here))
    town = movement.maps.get(here.map)
    if town is not None:
        x, y = min(x, town.width - 1), min(y, town.height - 1)
        y = next((row for row in range(y, town.height) if town.standing(x, row)), y)
    return MapTile(map=here.map, x=x, y=y)
