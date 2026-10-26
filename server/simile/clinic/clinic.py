import logging
from collections import Counter
from typing import TYPE_CHECKING

from simile.clinic.config import DEFAULT_CONFIG, ClinicConfig
from simile.economy import OUTSIDE, PLAYER, Kind
from simile.player.power import runs
from simile.player.where import here, location
from simile.protocol import Buyer, Fitting
from simile.schema import BODY_PARTS, PRESENT, SOLD, Bionic, Body, BodyPart, Mind, Player
from simile.sim import Clock
from simile.world.movement import Movement, inside

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)

KIDNEYS: tuple[BodyPart, ...] = ("left_kidney", "right_kidney")


class Clinic:
    """The doctor's trade, through the ledger: a kidney, recipes, and each bionic for money, a
    part of their body and, from a recipe, the parts it uses up."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        economy: "Economy",
        clock: Clock,
        config: ClinicConfig = DEFAULT_CONFIG,
    ) -> None:
        self.player = player
        self.movement = movement
        self.economy = economy
        self.clock = clock
        self.config = config

    def inside(self) -> bool:
        at, clinic = here(self.movement), location(self.movement, self.config.place)
        return at is not None and clinic is not None and inside(clinic, at)

    def parts(self) -> dict[BodyPart, float]:
        """What the doctor would buy of the player's body: one kidney, while they have both."""
        body = self.player.body
        if any(getattr(body, kidney) != PRESENT for kidney in KIDNEYS):
            return {}
        return {KIDNEYS[0]: self.config.kidney}

    def fittings(self) -> list[Fitting]:
        """What the doctor would fit now, whether or not they can pay or have the parts: stage 1's
        legs in stock, and each bionic they know the recipe for, once the cell's in and while it
        would run it."""
        return [*self._offered(), *self._from_recipes()]

    def _offered(self) -> list[Fitting]:
        body, offers = self.player.body, self.config.offers
        carried = {item.id for item in self.player.items}
        fittings = []
        for bionic, offer in offers.items():
            takes = offer.after or (PRESENT,)
            free = [p for p in BODY_PARTS if p in bionic.replaces and getattr(body, p) in takes]
            short = offer.needs is not None and offer.needs.id not in carried
            if bionic in body.bionics or short or not free or not self._stocked(bionic):
                continue
            fittings.append(Fitting(bionic=bionic, name=offer.name, price=offer.price, parts=free))
        return fittings

    def _from_recipes(self) -> list[Fitting]:
        body, known = self.player.body, self.player.mind.recipes
        fittings = []
        for bionic, recipe in self.config.recipes.items():
            if bionic not in known or body.has(bionic) or not recipe.ready(body):
                continue
            if not runs(body, bionic):
                continue
            lower = bionic.line[: bionic.line.index(bionic)]
            free = [part for part in recipe.replaces if getattr(body, part) in (PRESENT, *lower)]
            if free and self._stocked(bionic):
                fittings.append(
                    Fitting(bionic=bionic, name=recipe.name, price=recipe.credits, parts=free)
                )
        return fittings

    def _stocked(self, bionic: Bionic) -> bool:
        return self.config.stock.get(bionic, 0) >= 1

    def _uses(self, bionic: Bionic) -> dict[str, int]:
        """The items fitting `bionic` uses up, how many of each by id."""
        if recipe := self.config.recipes.get(bionic):
            return recipe.parts
        offer = self.config.offers.get(bionic)
        return {offer.needs.id: 1} if offer and offer.needs else {}

    def missing(self, bionic: Bionic) -> dict[str, int]:
        """How many of each item fitting `bionic` uses up they're short of."""
        carried = Counter(item.id for item in self.player.items)
        return {id: n - carried[id] for id, n in self._uses(bionic).items() if carried[id] < n}

    def recipes(self) -> dict[Bionic, float]:
        """What the doctor would pay, once, for each recipe they know and haven't sold her."""
        mind, procedures = self.player.mind, self.config.procedures
        return {
            bionic: buys
            for bionic in mind.recipes
            if bionic not in mind.sold
            and bionic in procedures
            and (buys := procedures[bionic].buys) is not None
        }

    def keep(self, buyer: Buyer) -> Buyer:
        """The clinic's buyer with what the doctor would buy of their body and mind, and fit."""
        update = {"parts": self.parts(), "fittings": self.fittings(), "recipes": self.recipes()}
        return buyer.model_copy(update=update)

    def sell_part(self, part: BodyPart) -> bool:
        """The player sells a part of their body to the doctor, if they'd buy it. Whether sold."""
        price = self.parts().get(part)
        if price is None or not self.inside():
            return False
        self.economy.pay(OUTSIDE, PLAYER, price, Kind.SALVAGE, self.config.place)
        self._change(part, SOLD)
        logger.info("%s  The player sells their %s to the doctor", self.clock, part)
        return True

    def sell_recipe(self, bionic: Bionic) -> bool:
        """The player sells the doctor a recipe they know, once. They still know it."""
        price = self.recipes().get(bionic)
        if price is None or not self.inside():
            return False
        self.economy.pay(OUTSIDE, PLAYER, price, Kind.SALVAGE, self.config.place)
        mind = self.player.mind
        self.player.mind = Mind(recipes=mind.recipes, sold=[*mind.sold, bionic])
        logger.info("%s  The player sells the doctor their recipe for %s", self.clock, bionic)
        return True

    def fit(self, bionic: Bionic, part: BodyPart) -> bool:
        """The doctor fits `bionic` in place of `part`, for its price and any parts it uses up, if
        they can pay and have them."""
        fitting = next((f for f in self.fittings() if f.bionic is bionic), None)
        if fitting is None or part not in fitting.parts or not self.inside():
            return False
        if fitting.price > self.player.money + 1e-9 or self.missing(bionic):
            return False
        self.economy.pay(PLAYER, OUTSIDE, fitting.price, Kind.PURCHASE, self.config.place)
        self._use_up(self._uses(bionic))
        self._change(part, bionic)
        logger.info("%s  The doctor fits %s in place of the player's %s", self.clock, bionic, part)
        return True

    def _use_up(self, parts: dict[str, int]) -> None:
        left = dict(parts)
        items = []
        for item in self.player.items:
            if left.get(item.id, 0) > 0:
                left[item.id] -= 1
            else:
                items.append(item)
        self.player.items = items

    def _change(self, part: BodyPart, state: str) -> None:
        body = self.player.body.model_dump() | {part: state}
        self.player.body = Body.model_validate(body)
