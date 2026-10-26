"""The things to search in the world and the parts they hold: content/street/README.md's *Finds*."""

from collections.abc import Sequence
from typing import NamedTuple

from simile.schema import Bionic, Id, Interactable, InteractableKind, Item, ItemKind, Tile, TileArea
from simile.street.plan import Plan


def part(item_id: str, name: str, weight: float) -> Item:
    return Item(id=item_id, kind=ItemKind.PART, name=name, weight=weight)


LITHIUM_CELL = part("lithium_cell", "Lithium cell", 0.3)
CHARGE_CONTROLLER = part("charge_controller", "Charge controller", 0.2)
USB_C_CONNECTOR = part("usb_c_connector", "USB-C connector", 0.1)
COPPER_WIRE = Item(id="copper_wire", kind=ItemKind.SALVAGE, name="Copper wire", weight=1.5)
"""The same as the metro's salvage on the dead train's roof."""


def searchable(
    plan: Plan,
    thing_id: str,
    label: str,
    area: TileArea,
    stand: Sequence[Tile],
    items: Sequence[Item] = (),
    teaches: Bionic | None = None,
    kind: InteractableKind = InteractableKind.SEARCHABLE,
    money: float = 0.0,
) -> None:
    """Something searched once for the `items` and `money` it holds and the recipe it `teaches`."""
    plan.interactables.append(
        Interactable(
            id=thing_id,
            label=label,
            kind=kind,
            map=plan.id,
            area=area,
            stand=list(stand),
            items=list(items),
            money=money,
            teaches=teaches,
        )
    )


def under(area: TileArea) -> list[Tile]:
    """The cells along the bottom row of `area`, to stand at it from."""
    row = area.y + area.height - 1
    return [Tile(x=x, y=row) for x in range(area.x, area.x + area.width)]


RATION_BAR = Item(id="ration_bar", kind=ItemKind.FOOD, name="Ration bar", weight=0.2)


class Stash(NamedTuple):
    """A place to search in a resident's house, in a piece of its furniture, and the loose cash
    and things it holds."""

    house: Id
    piece: str
    label: str
    money: float
    items: tuple[Item, ...] = ()

    @property
    def id(self) -> Id:
        return f"{self.house}_{self.piece}"


def _by_id(*stashes: Stash) -> dict[Id, Stash]:
    return {stash.id: stash for stash in stashes}


STASHES: dict[Id, Stash] = _by_id(
    Stash("house_1", "kitchen", "Jar on the kitchen shelf", 5.0),
    Stash("house_1", "wardrobe", "Coat in the wardrobe", 3.0),
    Stash("house_2", "bed", "Under the mattress", 10.0),
    Stash("house_2", "kitchen", "Tea tin", 2.0, (RATION_BAR,)),
    Stash("house_3", "sofa", "Sofa cushions", 2.0),
    Stash("house_3", "bed", "Bedside drawer", 4.0),
    Stash("house_4", "wardrobe", "Handbag in the wardrobe", 6.0),
    Stash("house_4", "kitchen", "Kitchen drawer", 1.0, (RATION_BAR,)),
    Stash("house_5", "sofa", "Sofa cushions", 2.0),
    Stash("house_5", "kitchen", "Jar on the kitchen shelf", 3.0),
    Stash("house_6", "sofa", "Sofa cushions", 3.0),
    Stash("house_6", "kitchen", "Kitchen cupboard", 0.0, (RATION_BAR,)),
    Stash("house_7", "wardrobe", "Coat in the wardrobe", 7.0),
    Stash("house_7", "kitchen", "Kitchen drawer", 2.0),
    Stash("house_8", "kitchen", "Biscuit tin", 4.0),
    Stash("house_8", "sofa", "Sofa cushions", 1.0),
    Stash("house_9", "bed", "Bedside drawer", 5.0),
    Stash("house_10", "kitchen", "Kitchen drawer", 2.0, (RATION_BAR,)),
)
"""The places to search in the houses, and the loose cash in them: content/street/README.md's
*Houses*."""
