"""The abandoned metro station under the village: content/street/README.md's *The metro*."""

from simile.schema import (
    Door,
    Facing,
    Interactable,
    InteractableKind,
    Item,
    ItemKind,
    Location,
    LocationKind,
    MapTile,
    Tile,
    TileArea,
)
from simile.street.plan import Light, Pickup, Plan
from simile.street.village import GROUND, Building, street
from simile.world.map import SpotKind

METRO = "metro"
WIDTH = 110
ENTRANCE = MapTile(map="banyan_row", x=62, y=GROUND + 3)
"""The stairway down's door on the river promenade under Banyan Row."""
HALL = GROUND - 3
"""The ticket hall's row, a flight up from the platform."""
LANDING = HALL - 3
"""The row stood on at the top of the stairway, where the door arrives."""
ARRIVAL = MapTile(map=METRO, x=2, y=LANDING)

CLINIC = "clinic"
SCRAP_STALL = "scrap_stall"
SCRAP_TRADER = "metro_scrap_trader"
"""The scrap trader's stall spot, by their stall on the platform."""
DOCTOR = "clinic_doctor"
"""The doctor's stall spot, in the clinic."""
PLUG = "metro_plug"
LIFT = "metro_lift"
DEAD_TERMINAL = "metro_terminal"
HIGH_LEDGE = "metro_high_ledge"
LIFT_FOOT = MapTile(map=METRO, x=100, y=GROUND)
"""Where the lift down to the sewers stops on the metro."""
LEGS_ROWS = 3
"""Rows up the high ledge assumes the hydraulic legs jump: one more than today's."""

SALVAGE = "salvage"
SECRET = "secret"
RATION_PACK = Item(id="ration_pack", kind=ItemKind.FOOD, name="Ration pack", weight=0.5)


def catwalk(plan: Plan, x: int, row: int, width: int) -> None:
    """A deck standing on row `row`, drawn as a steel catwalk over its solid row."""
    plan.fill(x, row + 1, width, 1)
    plan.piece("catwalk", x, row, width, 2)


def machine(plan: Plan, item_id: str, label: str, area: TileArea, stand: list[Tile]) -> None:
    kind = InteractableKind.MACHINE
    plan.interactables.append(
        Interactable(id=item_id, label=label, kind=kind, map=plan.id, area=area, stand=stand)
    )


def light(plan: Plan, light_id: str, x: int, y: int, width: int, height: int, lit: bool) -> None:
    area = TileArea(x=x, y=y, width=width, height=height)
    plan.light.append(Light(light_id, area, lit))


def salvage(plan: Plan, number: int, x: int, y: int) -> None:
    plan.pickups.append(Pickup(f"metro_salvage_{number}", SALVAGE, x, y))


def secret(
    plan: Plan, secret_id: str, x: int, y: int, money: float = 0.0, item: Item | None = None
) -> None:
    plan.pickups.append(Pickup(secret_id, SECRET, x, y, money, item))


def flight(plan: Plan, foot: tuple[int, int], rows: int) -> None:
    """Stairs rising west from `foot`, drawn as the metro's tiled steps over the street's."""
    x, y = foot
    plan.stairs(foot, east=False, steps=rows - 1)
    plan.piece("metro_steps", x - rows, y - rows, rows + 1, rows + 1)


def entrance(plan: Plan) -> None:
    """A landing, two flights down to the platform, and a catwalk over the first."""
    plan.fill(0, HALL + 1, 20, GROUND - HALL)
    plan.fill(0, LANDING + 1, 5, HALL - LANDING)
    flight(plan, (7, HALL), HALL - LANDING)
    flight(plan, (22, GROUND), GROUND - HALL)
    catwalk(plan, 7, LANDING - 2, 2)
    secret(plan, "metro_secret_stairwell", 8, LANDING - 2, money=25.0)
    plan.piece("turnstile", 11, HALL, 2, 1)
    plan.piece("ticket_machine", 15, HALL - 1, 1, 2)


def platform(plan: Plan) -> None:
    """The scrap stall, and a dead train with a catwalk a jump above its roof."""
    plan.piece("scrap_stall", 25, GROUND - 1, 3, 2)
    plan.spot(SCRAP_TRADER, SpotKind.STANDING, 26, GROUND, Facing.SOUTH)
    plan.locations.append(
        Location(
            id=SCRAP_STALL,
            name="The scrap trader's stall",
            kind=LocationKind.AMENITY,
            map=plan.id,
            area=TileArea(x=24, y=GROUND - 2, width=5, height=3),
            entry=Tile(x=28, y=GROUND),
        )
    )
    plan.piece("metro_bench", 29, GROUND, 2, 1)
    roof = GROUND - 3
    plan.piece("train_carriage", 33, roof + 1, 10, GROUND - roof)
    plan.fill(33, roof + 1, 10, 1)
    plan.ladder((32, GROUND), GROUND - roof)
    salvage(plan, 1, 38, roof)
    catwalk(plan, 45, roof - 2, 8)
    secret(plan, "metro_secret_catwalk", 52, roof - 2, money=40.0)
    plan.piece("crates", 44, GROUND, 1, 1)
    plan.piece("metro_bench", 49, GROUND, 2, 1)
    plan.piece("tunnel_arch", 55, GROUND - 7, 3, 8)


def tunnel(plan: Plan) -> None:
    """The plug's alcove between dark stretches, and a climb up the wall to the alcove."""
    plan.piece("pipes", 59, GROUND - 3, 12, 1)
    plan.piece("rubble", 60, GROUND, 2, 1)
    salvage(plan, 2, 63, GROUND)
    plan.piece("bedroll", 65, GROUND, 2, 1)
    salvage(plan, 3, 68, GROUND)
    plan.piece("breaker_box", 72, GROUND - 1, 1, 2)
    area = TileArea(x=72, y=GROUND - 1, width=1, height=2)
    machine(plan, PLUG, "Maintenance plug", area, [Tile(x=72, y=GROUND)])
    ledge = GROUND - 3
    plan.ladder((75, GROUND), GROUND - ledge)
    catwalk(plan, 76, ledge, 3)
    salvage(plan, 4, 77, ledge)
    catwalk(plan, 81, ledge - 2, 2)
    catwalk(plan, 85, ledge - 4, 2)
    secret(plan, "metro_secret_alcove", 86, ledge - 4, item=RATION_PACK)
    plan.piece("rubble", 79, GROUND, 2, 1)
    salvage(plan, 5, 83, GROUND)


def depot(plan: Plan) -> list[Plan]:
    """The clinic, the lift, the dead terminal and the high ledge."""
    clinic = Building(plan, CLINIC, "The Clinic", LocationKind.AMENITY, 88, 10, ("clinic",))
    clinic.door(1)
    clinic.place(entry=3)
    [room] = clinic.floors
    room.spot(DOCTOR, SpotKind.STANDING, 6, 2, Facing.SOUTH)
    plan.piece("freight_lift", LIFT_FOOT.x, GROUND - 3, 2, 4)
    area = TileArea(x=LIFT_FOOT.x, y=GROUND - 3, width=2, height=4)
    stand = [Tile(x=LIFT_FOOT.x, y=GROUND), Tile(x=LIFT_FOOT.x + 1, y=GROUND)]
    machine(plan, LIFT, "Maintenance lift", area, stand)
    plan.piece("dead_terminal", 104, GROUND - 1, 1, 2)
    area = TileArea(x=104, y=GROUND - 1, width=1, height=2)
    machine(plan, DEAD_TERMINAL, "Dead terminal", area, [Tile(x=104, y=GROUND)])
    ledge = GROUND - LEGS_ROWS
    catwalk(plan, 106, ledge, 4)
    area = TileArea(x=106, y=ledge, width=4, height=1)
    machine(plan, HIGH_LEDGE, "High ledge", area, [Tile(x=x, y=ledge) for x in range(106, 110)])
    plan.piece("crates", 108, ledge, 1, 1)
    salvage(plan, 6, 108, ledge)
    return clinic.floors


def lighting(plan: Plan) -> None:
    """Every cell in one stretch, lit or dark."""
    height = plan.height
    light(plan, "metro_entrance", 0, 0, 19, height, lit=True)
    light(plan, "metro_vault", 19, 0, 39, GROUND - 3, lit=False)
    light(plan, "metro_platform", 19, GROUND - 3, 39, height - GROUND + 3, lit=True)
    light(plan, "metro_tunnel_west", 58, 0, 13, height, lit=False)
    light(plan, "metro_maintenance", 71, 0, 3, height, lit=True)
    light(plan, "metro_tunnel_east", 74, 0, 13, height, lit=False)
    light(plan, "metro_depot", 87, 0, WIDTH - 87, height, lit=True)


def metro(village: Plan) -> list[Plan]:
    """The metro and the clinic's floor, joined to `village`, the street its stairway is on."""
    plan = street(METRO, "The Old Metro", WIDTH)
    entrance(plan)
    platform(plan)
    tunnel(plan)
    floors = depot(plan)
    lighting(plan)
    door = Door(id=f"{village.id}_to_{METRO}", outside=ENTRANCE, inside=ARRIVAL)
    village.doors.append(door)
    plan.doors.append(door)
    village.piece("metro_entrance", ENTRANCE.x - 1, ENTRANCE.y - 2, 1, 3)
    return [plan, *floors]
