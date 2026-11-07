import logging
import math
from collections.abc import Collection

from simile.clinic.config import DEFAULT_CONFIG
from simile.machines.materials import plastic
from simile.machines.workshop import Offer, Workshop
from simile.player.pickups import joined
from simile.schema import Id, Item, ItemKind, Player, Product
from simile.street.finds import COPPER_PIPE, COPPER_WIRE

logger = logging.getLogger(__name__)

WIRE_A_PIPE = 2


def _is_scrap(item: Item, kept: Collection[Id]) -> bool:
    return item.kind is ItemKind.SALVAGE and item.id not in kept


def _press(player: Player, kept: Collection[Id]) -> Product | None:
    """All the scrap they carry at 1 plastic a kilo, or None if a `Product` couldn't hold it."""
    kilos = sum(item.load for item in player.items if _is_scrap(item, kept))
    if not 0 < kilos < math.inf:
        return None
    return Product(item=plastic(kilos), uses="scrap", cost=kilos)


def _fits(player: Player, product: Product) -> bool:
    return player.load - product.cost + product.item.load <= player.carry_limit + 1e-9


def _make(player: Player, kept: Collection[Id]) -> bool:
    press = _press(player, kept)
    if press is None or not _fits(player, press):
        return False
    player.items = joined(
        (item for item in player.items if not _is_scrap(item, kept)), [press.item]
    )
    logger.info("The player recycles %s kg of scrap", press.cost)
    return True


def _is_pipe(item: Item) -> bool:
    return item.id == COPPER_PIPE.id


def _draw(player: Player) -> Product | None:
    """All the copper pipe they carry as wire, or None if a `Product` couldn't hold it."""
    pipes = [item for item in player.items if _is_pipe(item)]
    kilos = sum(item.load for item in pipes)
    if not 0 < kilos < math.inf:
        return None
    wire = COPPER_WIRE.model_copy(update={"amount": float(WIRE_A_PIPE * len(pipes))})
    return Product(item=wire, uses="scrap", cost=kilos)


def _make_wire(player: Player) -> bool:
    draw = _draw(player)
    if draw is None or not _fits(player, draw):
        return False
    wire = [COPPER_WIRE.model_copy() for _ in range(int(draw.item.amount))]
    player.items = joined((item for item in player.items if not _is_pipe(item)), wire)
    logger.info("The player draws %s copper wire", len(wire))
    return True


def offers(workshop: Workshop) -> None:
    recipes = DEFAULT_CONFIG.recipes.values()
    needed = [*(recipe.parts for recipe in recipes), *(m.parts for m in workshop.broken.values())]
    kept = frozenset(id for parts in needed for id in parts) | {COPPER_PIPE.id}
    workshop.offer(
        "recycler",
        Offer(lambda player: _press(player, kept), lambda player: _make(player, kept)),
        Offer(_draw, _make_wire),
    )
