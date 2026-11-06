from simile.clinic.config import DEFAULT_CONFIG as CLINIC
from simile.economy.config import DEFAULT_CONFIG as ECONOMY
from simile.icons.catalogue import ICONS, ITEMS, TRADES, UNKNOWN
from simile.player.config import DEFAULT_CONFIG as PLAYER
from simile.schema import lamp
from simile.story.lens import LENS
from simile.street import finds, sewers
from simile.street.metro import RATION_PACK
from simile.world.map import level_count, load_maps

WAITING_ON_Q13 = {"metal_sheet", "linear_actuator", "plastic", "plastic_pistol", "plastic_rounds"}
"""In the world before their pictures: Q13 paints them and deletes this (#601, #603, #609)."""


def in_the_world() -> set[str]:
    found = set()
    for level in range(level_count()):
        for town in load_maps(level=level).values():
            found |= {pickup.item.id for pickup in town.pickups if pickup.item}
            found |= {item.id for thing in town.interactables for item in thing.items}
    return found - WAITING_ON_Q13


def every_item() -> set[str]:
    defined = [
        lamp(),
        RATION_PACK,
        LENS,
        sewers.APEX_ACTUATOR,
        sewers.APEX_BOARD,
        sewers.GAUGE,
        *sewers.SALVAGE_ITEMS,
        finds.LITHIUM_CELL,
        finds.CHARGE_CONTROLLER,
        finds.USB_C_CONNECTOR,
        finds.COPPER_WIRE,
        *(salvage.item for salvage in PLAYER.salvage.values()),
    ]
    parts = {id for recipe in CLINIC.recipes.values() for id in recipe.parts}
    priced = set(ECONOMY.salvage) | set(ECONOMY.parts) | ECONOMY.kept
    return {item.id for item in defined} | parts | priced | in_the_world()


def test_every_item_the_server_defines_has_a_picture() -> None:
    assert every_item() - ICONS.keys() == set()


def test_the_items_pictures_cover_every_item_and_one_for_any_without() -> None:
    assert every_item() <= {icon.id for icon in ITEMS}
    assert UNKNOWN.id not in every_item()


def test_the_trade_screen_has_a_picture_for_talking_selling_everything_and_each_treatment() -> None:
    treatments = {"patch_up"} | {f"treat_{effect.value}" for effect in CLINIC.cures}
    assert {icon.id for icon in TRADES} == {"talk", "sell_everything"} | treatments
