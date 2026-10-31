import logging
import math
from collections import Counter
from typing import TYPE_CHECKING

from simile.clinic.config import DEFAULT_CONFIG, ClinicConfig
from simile.economy import OUTSIDE, PLAYER, Kind
from simile.player.health import KIDNEYS
from simile.player.power import runs
from simile.player.where import here, location
from simile.protocol import Buyer, Fitting, Treatment
from simile.schema import (
    PRESENT,
    SOLD,
    Bionic,
    Body,
    BodyPart,
    EffectKind,
    Mind,
    Player,
)
from simile.sim import Clock
from simile.world.movement import Movement, inside

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)


class Clinic:
    """The doctor's trade, through the ledger: a kidney, recipes, each bionic for money, a part of
    their body and, from a recipe, the parts it uses up, and treating them."""

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
        """Each bionic they know the recipe for and haven't fitted, whether or not they can pay or
        have the parts, `blocked` with why the doctor can't fit it now."""
        body, known = self.player.body, self.player.mind.recipes
        fittings = []
        for bionic, recipe in self.config.recipes.items():
            if bionic not in known or body.has(bionic):
                continue
            lower = bionic.line[: bionic.line.index(bionic)]
            free = [part for part in recipe.replaces if getattr(body, part) in (PRESENT, *lower)]
            if free:
                blocked = self._blocked(bionic)
                fitting = Fitting(bionic=bionic, name=recipe.name, price=recipe.credits, parts=free)
                fittings.append(fitting.model_copy(update={"blocked": blocked}))
        return fittings

    def _blocked(self, bionic: Bionic) -> str | None:
        recipes, body = self.config.recipes, self.player.body
        if first := [b for b in recipes[bionic].after if not body.has(b)]:
            names = [
                recipes[b].name.lower() if b in recipes else b.replace("_", " ") for b in first
            ]
            return f"Needs a {' and a '.join(names)} first."
        if not runs(body, bionic):
            return "Needs a bigger power cell first."
        if not self._stocked(bionic):
            return "Out of stock."
        return None

    def _stocked(self, bionic: Bionic) -> bool:
        return self.config.stock.get(bionic, 0) >= 1

    def _uses(self, bionic: Bionic) -> dict[str, int]:
        """The items fitting `bionic` uses up, how many of each by id."""
        recipe = self.config.recipes.get(bionic)
        return recipe.parts if recipe else {}

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

    def treatments(self) -> list[Treatment]:
        """What the doctor would treat now: patching them up while they're hurt, and each effect
        they have that she cures."""
        found = []
        if (hurt := 1 - self.player.health) > 1e-9:
            price = math.ceil(self.config.patch_up * hurt - 1e-9)
            found.append(Treatment(effect=None, name=self.config.patch_name, price=price))
        for effect in self.player.effects:
            if cure := self.config.cures.get(effect.kind):
                found.append(Treatment(effect=effect.kind, name=cure.name, price=cure.price))
        return found

    def keep(self, buyer: Buyer) -> Buyer:
        """The clinic's buyer with what the doctor would buy of their body and mind, fit and
        treat."""
        update = {
            "parts": self.parts(),
            "fittings": self.fittings(),
            "recipes": self.recipes(),
            "treatments": self.treatments(),
        }
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
        if fitting.blocked:
            logger.info("%s  The doctor won't fit %s: %s", self.clock, bionic, fitting.blocked)
            return False
        if fitting.price > self.player.money + 1e-9 or self.missing(bionic):
            return False
        self.economy.pay(PLAYER, OUTSIDE, fitting.price, Kind.PURCHASE, self.config.place)
        self._use_up(self._uses(bionic))
        self._change(part, bionic)
        logger.info("%s  The doctor fits %s in place of the player's %s", self.clock, bionic, part)
        return True

    def treat(self, effect: EffectKind | None) -> bool:
        """The doctor treats `effect`, or with None patches them up to full health, if they can
        pay. Whether she did."""
        treatment = next((t for t in self.treatments() if t.effect == effect), None)
        if treatment is None or not self.inside() or treatment.price > self.player.money + 1e-9:
            return False
        self.economy.pay(PLAYER, OUTSIDE, treatment.price, Kind.PURCHASE, self.config.place)
        if effect is None:
            self.player.health = 1.0
        else:
            self.player.effects = [e for e in self.player.effects if e.kind is not effect]
        logger.info("%s  The doctor gives the player %s", self.clock, treatment.name.lower())
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
