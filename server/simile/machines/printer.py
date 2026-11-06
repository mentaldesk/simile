"""The 3D printer's offers: README.md."""

import logging
from collections.abc import Callable, Sequence

from simile.machines.workshop import Offer, Workshop
from simile.player.pickups import joined
from simile.schema import Item, ItemKind, Material, Player, Product

logger = logging.getLogger(__name__)

PISTOL = Item(
    id="plastic_pistol",
    kind=ItemKind.WEAPON,
    name="Plastic pistol",
    weight=0.5,
    material=Material.PLASTIC,
    rounds=0,
    capacity=6,
    condition=1.0,
)
ROUNDS = Item(
    id="plastic_rounds",
    kind=ItemKind.ROUNDS,
    name="Plastic rounds",
    weight=0.02,
    amount=6.0,
    material=Material.PLASTIC,
)
PRODUCTS = (
    Product(item=PISTOL, uses=Material.PLASTIC, cost=6),
    Product(item=ROUNDS, uses=Material.PLASTIC, cost=2),
)


def _without(items: Sequence[Item], material: str, cost: float) -> list[Item]:
    kept: list[Item] = []
    for item in items:
        if item.id != material:
            kept.append(item)
            continue
        taken = min(cost, item.amount)
        cost -= taken
        if item.amount - taken > 1e-9:
            kept.append(item.model_copy(update={"amount": item.amount - taken}))
    return kept


def _printing(product: Product) -> Callable[[Player], bool]:
    def make(player: Player) -> bool:
        stacks = [item for item in player.items if item.id == product.uses]
        if sum(stack.amount for stack in stacks) < product.cost - 1e-9:
            return False
        after = player.load - product.cost * stacks[0].weight + product.item.load
        if after > player.carry_limit + 1e-9:
            return False
        rest = _without(player.items, product.uses, product.cost)
        player.items = joined(rest, [product.item.model_copy()])
        logger.info("The player prints %s", product.item.name)
        return True

    return make


def offers(workshop: Workshop) -> None:
    for product in PRODUCTS:
        workshop.offer("printer_3d", Offer(product, _printing(product)))
