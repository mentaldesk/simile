import logging
import math
from collections.abc import Collection

from simile.clinic.config import DEFAULT_CONFIG
from simile.machines.materials import plastic
from simile.machines.workshop import Offer, Workshop
from simile.schema import Id, Item, ItemKind, Player, Product

logger = logging.getLogger(__name__)


def _is_scrap(item: Item, kept: Collection[Id]) -> bool:
    return item.kind is ItemKind.SALVAGE and item.id not in kept


def _press(player: Player, kept: Collection[Id]) -> Product | None:
    """All the scrap they carry at 1 plastic a kilo, or None if a `Product` couldn't hold it."""
    kilos = sum(item.load for item in player.items if _is_scrap(item, kept))
    if not 0 < kilos < math.inf:
        return None
    return Product(item=plastic(kilos), uses="scrap", cost=kilos)


def _make(player: Player, kept: Collection[Id]) -> bool:
    press = _press(player, kept)
    if press is None or player.load - press.cost + press.item.load > player.carry_limit + 1e-9:
        return False
    items = [item for item in player.items if not _is_scrap(item, kept)]
    stack = next((item for item in items if item.id == press.item.id), None)
    if stack is None:
        player.items = [*items, press.item]
    else:
        joined = stack.model_copy(update={"amount": stack.amount + press.item.amount})
        player.items = [joined if item is stack else item for item in items]
    logger.info("The player recycles %s kg of scrap", press.cost)
    return True


def offers(workshop: Workshop) -> None:
    recipes = DEFAULT_CONFIG.recipes.values()
    needed = [*(recipe.parts for recipe in recipes), *(m.parts for m in workshop.broken.values())]
    kept = frozenset(id for parts in needed for id in parts)
    workshop.offer(
        "recycler", Offer(lambda player: _press(player, kept), lambda player: _make(player, kept))
    )
