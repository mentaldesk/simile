"""Until P6 puts recipes and their parts in the world and P19 plays the loop in stage 2's order,
the loop hands the player what the clinic needs for the spring feet, the datajack and the eye.
Delete with P19."""

from simile.clinic.config import DEFAULT_CONFIG
from simile.player.config import DEFAULT_CONFIG as PLAYER_CONFIG
from simile.schema import POWER_CELLS, Bionic, Body, Item, ItemKind, Mind, Player
from simile.street.sewers import SCRAP

WIRE = PLAYER_CONFIG.salvage["metro_salvage_1"].item
PARTS: dict[str, Item] = {
    WIRE.id: WIRE,
    **{id: SCRAP[id] for id in ("brass_fitting", "float_valve")},
    "usb_c_connector": Item(
        id="usb_c_connector", kind=ItemKind.PART, name="USB-C connector", weight=0.1
    ),
    "infrared_lens": Item(id="infrared_lens", kind=ItemKind.PART, name="Infrared lens", weight=0.1),
}


def learn(player: Player, bionic: Bionic) -> None:
    """Fits the power cell if it isn't in, and teaches them `bionic`'s recipe."""
    if not player.body.has(POWER_CELLS[0]):
        player.body = Body.model_validate(player.body.model_dump() | {"stomach": POWER_CELLS[0]})
    if bionic not in player.mind.recipes:
        mind = player.mind
        player.mind = Mind(recipes=[*mind.recipes, bionic], sold=mind.sold)


def carry(player: Player, bionic: Bionic) -> None:
    """Hands them the parts `bionic`'s recipe uses up."""
    parts = DEFAULT_CONFIG.recipes[bionic].parts
    player.items = [*player.items, *(PARTS[id] for id, n in parts.items() for _ in range(n))]
