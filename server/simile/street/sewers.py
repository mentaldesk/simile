"""A landing at the foot of the metro's maintenance lift, a placeholder until S9's sewers."""

from simile.schema import Door, Item, ItemKind, MapTile, TileArea
from simile.street.metro import LIFT_FOOT, METRO
from simile.street.plan import Plan
from simile.street.village import GROUND, street
from simile.world.map import Light

SEWERS = "sewers"
WIDTH = 12
LANDING = MapTile(map=SEWERS, x=2, y=GROUND)
"""Where the lift from the metro stops."""
APEX_ACTUATOR = Item(id="apex_actuator", kind=ItemKind.PART, name="Apex actuator", weight=2.0)
"""The part premium legs need, from Apex's own stock: S9 places it in a secret here."""


def sewers(metro: Plan) -> Plan:
    """The landing, joined to `metro` by its lift."""
    plan = street(SEWERS, "The Sewers", WIDTH)
    plan.piece("freight_lift", LANDING.x, GROUND - 3, 2, 4)
    plan.piece("pipes", 0, GROUND - 3, WIDTH, 1)
    plan.piece("rubble", 7, GROUND, 2, 1)
    area = TileArea(x=0, y=0, width=WIDTH, height=plan.height)
    plan.light.append(Light("sewers_landing", area, True))
    door = Door(id=f"{METRO}_to_{SEWERS}", outside=LIFT_FOOT, inside=LANDING)
    metro.doors.append(door)
    plan.doors.append(door)
    return plan
