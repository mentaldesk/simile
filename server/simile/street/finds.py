"""The things to search in the world and the parts they hold: content/street/README.md's *Finds*."""

from collections.abc import Sequence

from simile.schema import Bionic, Interactable, InteractableKind, Item, ItemKind, Tile, TileArea
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
) -> None:
    """Something searched once for the `items` it holds and the recipe it `teaches`."""
    plan.interactables.append(
        Interactable(
            id=thing_id,
            label=label,
            kind=kind,
            map=plan.id,
            area=area,
            stand=list(stand),
            items=list(items),
            teaches=teaches,
        )
    )


def under(area: TileArea) -> list[Tile]:
    """The cells along the bottom row of `area`, to stand at it from."""
    row = area.y + area.height - 1
    return [Tile(x=x, y=row) for x in range(area.x, area.x + area.width)]
