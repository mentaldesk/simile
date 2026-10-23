import logging
from typing import TYPE_CHECKING, get_args

from simile.clinic.config import DEFAULT_CONFIG, ClinicConfig
from simile.economy import OUTSIDE, PLAYER, Kind
from simile.player.where import here, location
from simile.protocol import Buyer, Fitting
from simile.schema import PRESENT, SOLD, Bionic, Body, BodyPart, Player
from simile.sim import Clock
from simile.world.movement import Movement, inside

if TYPE_CHECKING:
    from simile.economy.economy import Economy

logger = logging.getLogger(__name__)

KIDNEYS: tuple[BodyPart, ...] = ("left_kidney", "right_kidney")
PARTS: tuple[BodyPart, ...] = get_args(BodyPart.__value__)


class Clinic:
    """The doctor's trade, through the ledger: a kidney, and each bionic for money and a part."""

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
        """The bionics in stock the doctor could fit now, in place of a part or the legs before."""
        body, offers = self.player.body, self.config.offers
        carried = {item.id for item in self.player.items}
        fittings = []
        for bionic, offer in offers.items():
            fitted = bionic in body.bionics
            takes = offer.after or (PRESENT,)
            parts = [part for part in PARTS if part in bionic.replaces]
            free = [part for part in parts if getattr(body, part) in takes]
            short = offer.needs is not None and offer.needs.id not in carried
            if fitted or short or not free or self.config.stock.get(bionic, 0) < 1:
                continue
            fittings.append(Fitting(bionic=bionic, name=offer.name, price=offer.price, parts=free))
        return fittings

    def keep(self, buyer: Buyer) -> Buyer:
        """The clinic's buyer with what the doctor would buy of their body and fit."""
        return buyer.model_copy(update={"parts": self.parts(), "fittings": self.fittings()})

    def sell_part(self, part: BodyPart) -> bool:
        """The player sells a part of their body to the doctor, if they'd buy it. Whether sold."""
        price = self.parts().get(part)
        if price is None or not self.inside():
            return False
        self.economy.pay(OUTSIDE, PLAYER, price, Kind.SALVAGE, self.config.place)
        self._change(part, SOLD)
        logger.info("%s  The player sells their %s to the doctor", self.clock, part)
        return True

    def fit(self, bionic: Bionic, part: BodyPart) -> bool:
        """The doctor fits `bionic` in place of `part`, for its price, if they can pay."""
        fitting = next((f for f in self.fittings() if f.bionic is bionic), None)
        if fitting is None or part not in fitting.parts or not self.inside():
            return False
        if fitting.price > self.player.money + 1e-9:
            return False
        self.economy.pay(PLAYER, OUTSIDE, fitting.price, Kind.PURCHASE, self.config.place)
        if needs := self.config.offers[bionic].needs:
            items = list(self.player.items)
            items.remove(next(item for item in items if item.id == needs.id))
            self.player.items = items
        self._change(part, bionic)
        logger.info("%s  The doctor fits %s in place of the player's %s", self.clock, bionic, part)
        return True

    def _change(self, part: BodyPart, state: str) -> None:
        body = self.player.body.model_dump() | {part: state}
        self.player.body = Body.model_validate(body)
