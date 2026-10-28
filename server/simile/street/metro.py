"""The abandoned metro station under the village: content/street/README.md's *The metro*."""

from simile.player.config import SALVAGE as PLAYER_SALVAGE
from simile.schema import (
    Bionic,
    CreatureKind,
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
from simile.street.finds import (
    CHARGE_CONTROLLER,
    COPPER_WIRE,
    LITHIUM_CELL,
    USB_C_CONNECTOR,
    searchable,
    under,
)
from simile.street.jump import OWN_JUMP
from simile.street.plan import Pickup, Plan, Spawn
from simile.street.village import GROUND, Building, plug, street
from simile.world.map import Light, SpotKind

METRO = "metro"
DEPOT_END = 110
"""Where the depot ends and the freight siding begins."""
WIDTH = 230
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
LEDGE_ROWS = 3
"""Rows up the high ledge is: out of the player's own jump, and in the spring feet's."""
LEDGE_SECRET = "metro_secret_ledge"
ALCOVE_SECRET = "metro_secret_alcove"
GANTRY = GROUND - 7
"""The row the gantry over the west tunnel stands on, with three rows of room under its roof."""
GANTRY_SECRET = "metro_secret_gantry"
TICKET_MACHINE = "metro_ticket_machine"
FRIDGE = "metro_fridge"
CONTAINER = "metro_container"
FREIGHT_CRATES = "metro_freight_crates"
SWITCHBOARD = "metro_switchboard"
RELAY_RACK = "metro_relay_rack"
SIGNAL_DESK = "metro_signal_desk"
TOOL_CRATE = "metro_tool_crate"
LOCKERS = "metro_lockers"
TRACK_PLUG = "metro_track_plug"
SHED_PLUG = "metro_shed_plug"
STACK = 124
"""The west end of the two containers stacked on the siding, with a ladder up their side."""
CRANE = GROUND - 10
"""The row the crane's gantry over the siding stands on, four rows above the stacked containers."""
CRANE_SECRET = "metro_secret_crane"
DECK = GROUND - 4
"""The row the signal box's deck stands on."""
MEZZANINE = GROUND - 7
"""The row the shed's mezzanine and the top of the store room's wall stand on, three rows under
its roof, like the gantry."""
STORE_WALL = 218
"""The west end of the wall, three cells thick, between the shed and its store room, with the
jammed door at its foot."""
STORE_SECRET = "metro_secret_store"

SALVAGE = "salvage"
SECRET = "secret"
RATION_PACK = Item(id="ration_pack", kind=ItemKind.FOOD, name="Ration pack", weight=0.5)


_LYING = {salvage.item.id: salvage.item for salvage in PLAYER_SALVAGE.values()}
SCRAP_STEEL = _LYING["scrap_steel"]
CIRCUIT_BOARD = _LYING["circuit_board"]
BRASS_VALVE = _LYING["brass_valve"]
SIGNAL_RELAY = _LYING["signal_relay"]
SERVO_MOTOR = _LYING["servo_motor"]
BOTS = ((48, 44, 52), (38, 34, 43))
"""Each bot on the floor: where it starts, and the stretch it keeps to, west to east. The first
patrols under the vault's catwalk and the second under the train, and neither climbs, so the way
past both is overhead: up the ladder at 32 onto the train's roof, a jump up to the catwalk, and
off its east end onto the pipe ledge and down its ladder at 55, or the same back. On the floor,
each is jumped over as it comes."""
LEDGE = 53
"""The west end of the pipe ledge past the catwalk, a step down from it, with a ladder at its east
end down to the floor past the bots."""
BOT_SPAN = 2
"""Cells either side of where it starts that a bot patrols."""


def catwalk(plan: Plan, x: int, row: int, width: int) -> None:
    """A deck standing on row `row`, drawn as a steel catwalk over its solid row."""
    plan.fill(x, row + 1, width, 1)
    plan.piece("catwalk", x, row, width, 2)


def machine(
    plan: Plan,
    item_id: str,
    label: str,
    area: TileArea,
    stand: list[Tile],
    kind: InteractableKind = InteractableKind.MACHINE,
) -> None:
    plan.interactables.append(
        Interactable(id=item_id, label=label, kind=kind, map=plan.id, area=area, stand=stand)
    )


def light(plan: Plan, light_id: str, x: int, y: int, width: int, height: int, lit: bool) -> None:
    area = TileArea(x=x, y=y, width=width, height=height)
    plan.light.append(Light(light_id, area, lit))


def salvage(
    plan: Plan, number: int, x: int, y: int, needs: str | None = None, item: Item | None = None
) -> None:
    plan.pickups.append(Pickup(f"metro_salvage_{number}", SALVAGE, x, y, item=item, needs=needs))


def secret(
    plan: Plan,
    secret_id: str,
    x: int,
    y: int,
    needs: str,
    money: float = 0.0,
    item: Item | None = None,
) -> None:
    plan.pickups.append(Pickup(secret_id, SECRET, x, y, money, item, needs))


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
    secret(plan, "metro_secret_stairwell", 8, LANDING - 2, OWN_JUMP, money=25.0)
    plan.piece("turnstile", 11, HALL, 2, 1)
    plan.piece("ticket_machine", 15, HALL - 1, 1, 2)
    area = TileArea(x=15, y=HALL - 1, width=1, height=2)
    searchable(
        plan, TICKET_MACHINE, "Dead ticket machine", area, under(area), [COPPER_WIRE, LITHIUM_CELL]
    )


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
    secret(plan, "metro_secret_catwalk", 52, roof - 2, OWN_JUMP, money=40.0)
    catwalk(plan, LEDGE, roof, 2)
    plan.ladder((LEDGE + 2, GROUND), GROUND - roof)
    plan.piece("crates", 44, GROUND, 1, 1)
    plan.piece("metro_bench", 49, GROUND, 2, 1)
    plan.piece("tunnel_arch", 55, GROUND - 7, 3, 8)


def tunnel(plan: Plan) -> None:
    """The gantry, the plug's alcove between dark stretches, and a climb up the wall."""
    gantry(plan)
    plan.piece("pipes", 59, GROUND - 3, 12, 1)
    plan.piece("rubble", 60, GROUND, 2, 1)
    salvage(plan, 2, 63, GROUND)
    plan.piece("bedroll", 65, GROUND, 2, 1)
    salvage(plan, 3, 68, GROUND)
    plan.piece("fridge", 70, GROUND - 1, 1, 2)
    area = TileArea(x=70, y=GROUND - 1, width=1, height=2)
    searchable(plan, FRIDGE, "Dead fridge", area, under(area), [COPPER_WIRE, LITHIUM_CELL])
    plan.piece("breaker_box", 72, GROUND - 1, 1, 2)
    area = TileArea(x=72, y=GROUND - 1, width=1, height=2)
    plug(plan, PLUG, "Maintenance plug", area, Tile(x=72, y=GROUND))
    ledge = GROUND - 3
    plan.ladder((75, GROUND), GROUND - ledge)
    catwalk(plan, 76, ledge, 3)
    catwalk(plan, 81, ledge - 2, 2)
    alcove = ledge - 7
    catwalk(plan, 85, alcove, 2)
    salvage(plan, 4, 85, alcove, needs=Bionic.SPRING_FEET_2)
    secret(plan, ALCOVE_SECRET, 86, alcove, Bionic.SPRING_FEET_2, item=RATION_PACK)
    plan.piece("rubble", 79, GROUND, 2, 1)
    salvage(plan, 5, 83, GROUND)


def gantry(plan: Plan) -> None:
    """A gantry under a roof too low for the feet to rise, over a gap only the legs clear."""
    catwalk(plan, 73, GANTRY + 2, 2)
    catwalk(plan, 69, GANTRY, 4)
    catwalk(plan, 61, GANTRY, 3)
    plan.fill(58, GANTRY - 4, 16, 1)
    for x in (58, 66):
        plan.piece("pipes", x, GANTRY - 4, 8, 1)
    secret(plan, GANTRY_SECRET, 61, GANTRY, Bionic.BIONIC_LEGS, money=60.0)


def depot(plan: Plan) -> list[Plan]:
    """The clinic, the lift, the dead terminal and the high ledge."""
    clinic = Building(plan, CLINIC, "The Clinic", LocationKind.AMENITY, 88, 10, ("clinic",))
    clinic.door(1)
    clinic.place(entry=3)
    [room] = clinic.floors
    room.spot(DOCTOR, SpotKind.STANDING, 6, 2, Facing.SOUTH)
    plan.piece("freight_lift", LIFT_FOOT.x, GROUND - 3, 2, 4)
    area = TileArea(x=LIFT_FOOT.x, y=GROUND - 3, width=2, height=4)
    stand = [Tile(x=LIFT_FOOT.x, y=LIFT_FOOT.y)]
    machine(plan, LIFT, "Maintenance lift", area, stand, InteractableKind.JACK)
    plan.piece("dead_terminal", 104, GROUND - 1, 1, 2)
    area = TileArea(x=104, y=GROUND - 1, width=1, height=2)
    stand = [Tile(x=104, y=GROUND)]
    machine(plan, DEAD_TERMINAL, "Dead terminal", area, stand, InteractableKind.JACK)
    ledge = GROUND - LEDGE_ROWS
    catwalk(plan, 106, ledge, 4)
    area = TileArea(x=106, y=ledge, width=4, height=1)
    machine(plan, HIGH_LEDGE, "High ledge", area, [Tile(x=x, y=ledge) for x in range(106, 110)])
    plan.piece("crates", 108, ledge, 1, 1)
    salvage(plan, 6, 108, ledge, needs=Bionic.SPRING_FEET)
    secret(plan, LEDGE_SECRET, 106, ledge, Bionic.SPRING_FEET, money=60.0)
    return clinic.floors


def siding(plan: Plan) -> None:
    """Crates, two containers stacked under a crane's gantry, and one beside them."""
    plan.piece("tunnel_arch", 112, GROUND - 7, 3, 8)
    plan.piece("crates", 119, GROUND, 1, 1)
    area = TileArea(x=119, y=GROUND, width=1, height=1)
    searchable(plan, FREIGHT_CRATES, "Freight crates", area, under(area), [CHARGE_CONTROLLER])
    low, high = GROUND - 2, GROUND - 5
    plan.piece("shipping_container", STACK, low, 6, 3)
    plan.fill(STACK, low, 6, 1)
    plan.piece("shipping_container", STACK, high, 6, 3)
    plan.fill(STACK, high, 6, 3)
    plan.ladder((STACK - 1, GROUND), GROUND - high + 1)
    area = TileArea(x=STACK, y=low, width=6, height=3)
    searchable(
        plan, CONTAINER, "Shipping container", area, under(area), [SERVO_MOTOR, LITHIUM_CELL]
    )
    plan.piece("shipping_container", 132, low, 6, 3)
    plan.fill(132, low, 6, 1)
    secret(plan, "metro_secret_container", 135, low - 1, OWN_JUMP, money=20.0)
    catwalk(plan, 131, CRANE, 8)
    secret(plan, CRANE_SECRET, 132, CRANE, Bionic.SPRING_FEET, money=40.0)
    salvage(plan, 10, 137, CRANE, Bionic.SPRING_FEET, SERVO_MOTOR)
    salvage(plan, 7, 139, GROUND, item=SCRAP_STEEL)


def signal_box(plan: Plan) -> None:
    """A deck up a ladder with dead switchboards and the signal desk, a jack."""
    catwalk(plan, 142, DECK, 12)
    plan.ladder((141, GROUND), GROUND - DECK)
    plan.piece("switchboard", 143, DECK - 1, 2, 2)
    area = TileArea(x=143, y=DECK - 1, width=2, height=2)
    held = [COPPER_WIRE, COPPER_WIRE, SIGNAL_RELAY]
    searchable(plan, SWITCHBOARD, "Dead switchboard", area, under(area), held)
    plan.piece("switchboard", 146, DECK - 1, 2, 2)
    area = TileArea(x=146, y=DECK - 1, width=2, height=2)
    searchable(plan, RELAY_RACK, "Relay rack", area, under(area), [USB_C_CONNECTOR])
    plan.piece("dead_terminal", 150, DECK - 1, 1, 2)
    area = TileArea(x=150, y=DECK - 1, width=1, height=2)
    held = [CIRCUIT_BOARD, CIRCUIT_BOARD]
    searchable(
        plan, SIGNAL_DESK, "Signal desk", area, under(area), held, kind=InteractableKind.JACK
    )
    salvage(plan, 8, 152, DECK, item=CIRCUIT_BOARD)


def track(plan: Plan) -> None:
    """The disused track into the dark, a plug halfway, and a ledge a hop above a pipe ledge."""
    plan.piece("tunnel_arch", 156, GROUND - 7, 3, 8)
    plan.piece("pipes", 160, GROUND - 3, 14, 1)
    plan.piece("rubble", 163, GROUND, 2, 1)
    plan.piece("crates", 168, GROUND, 1, 1)
    area = TileArea(x=168, y=GROUND, width=1, height=1)
    searchable(plan, TOOL_CRATE, "Tool crate", area, under(area), [COPPER_WIRE, LITHIUM_CELL])
    salvage(plan, 9, 174, GROUND, item=SIGNAL_RELAY)
    plan.piece("breaker_box", 181, GROUND - 1, 1, 2)
    area = TileArea(x=181, y=GROUND - 1, width=1, height=2)
    plug(plan, TRACK_PLUG, "Track plug", area, Tile(x=181, y=GROUND))
    plan.ladder((188, GROUND), 3)
    catwalk(plan, 189, GROUND - 3, 3)
    catwalk(plan, 194, GROUND - 5, 2)
    secret(plan, "metro_secret_tunnel", 195, GROUND - 5, OWN_JUMP, money=10.0)
    plan.piece("bedroll", 197, GROUND, 2, 1)
    plan.piece("rubble", 201, GROUND, 2, 1)


def shed(plan: Plan) -> None:
    """The maintenance shed, and its store room behind a jammed door, reached over its wall from a
    mezzanine across a gap that only the legs clear, as the gantry's nook is."""
    roof = MEZZANINE - 4
    plan.fill(205, roof, WIDTH - 205, 1)
    for x, width in ((205, 12), (217, WIDTH - 217)):
        plan.piece("pipes", x, roof, width, 1)
    plan.piece("breaker_box", 208, GROUND - 1, 1, 2)
    area = TileArea(x=208, y=GROUND - 1, width=1, height=2)
    plug(plan, SHED_PLUG, "Shed plug", area, Tile(x=208, y=GROUND))
    plan.piece("lockers", 210, GROUND - 1, 2, 2)
    area = TileArea(x=210, y=GROUND - 1, width=2, height=2)
    searchable(plan, LOCKERS, "Tool lockers", area, under(area), [RATION_PACK])
    plan.ladder((207, GROUND), GROUND - MEZZANINE)
    catwalk(plan, 208, MEZZANINE, 5)
    plan.fill(STORE_WALL, MEZZANINE + 1, 3, GROUND - MEZZANINE)
    plan.piece("bulkhead", STORE_WALL, MEZZANINE + 1, 3, GROUND - MEZZANINE + 2)
    plan.ladder((STORE_WALL + 3, GROUND), GROUND - MEZZANINE)
    salvage(plan, 11, 224, GROUND, Bionic.BIONIC_LEGS, BRASS_VALVE)
    plan.piece("crates", 227, GROUND, 1, 1)
    secret(plan, STORE_SECRET, 228, GROUND, Bionic.BIONIC_LEGS, money=50.0)


def bots(plan: Plan) -> None:
    for number, (x, west, east) in enumerate(BOTS, 1):
        area = TileArea(x=west, y=GROUND, width=east - west + 1, height=1)
        bot = Spawn(f"metro_bot_{number}", CreatureKind.BOT, x, GROUND, area, BOT_SPAN)
        plan.creatures.append(bot)


def lighting(plan: Plan) -> None:
    """Every cell in one stretch, lit or dark."""
    height = plan.height
    light(plan, "metro_entrance", 0, 0, 19, height, lit=True)
    light(plan, "metro_vault", 19, 0, 39, GROUND - 3, lit=False)
    light(plan, "metro_platform", 19, GROUND - 3, 39, height - GROUND + 3, lit=True)
    light(plan, "metro_gantry", 58, 0, 13, GANTRY + 2, lit=True)
    light(plan, "metro_tunnel_west", 58, GANTRY + 2, 13, height - GANTRY - 2, lit=False)
    light(plan, "metro_maintenance", 71, 0, 3, height, lit=True)
    light(plan, "metro_tunnel_east", 74, 0, 13, height, lit=False)
    light(plan, "metro_depot", 87, 0, DEPOT_END - 87, height, lit=True)
    light(plan, "metro_siding", DEPOT_END, 0, 156 - DEPOT_END, height, lit=True)
    light(plan, "metro_track_west", 156, 0, 24, height, lit=False)
    light(plan, "metro_track_alcove", 180, 0, 3, height, lit=True)
    light(plan, "metro_track_east", 183, 0, 23, height, lit=False)
    light(plan, "metro_shed", 206, 0, WIDTH - 206, height, lit=True)


def metro(village: Plan) -> list[Plan]:
    """The metro and the clinic's floor, joined to `village`, the street its stairway is on."""
    plan = street(METRO, "The Old Metro", WIDTH)
    entrance(plan)
    platform(plan)
    tunnel(plan)
    floors = depot(plan)
    siding(plan)
    signal_box(plan)
    track(plan)
    shed(plan)
    bots(plan)
    lighting(plan)
    door = Door(id=f"{village.id}_to_{METRO}", outside=ENTRANCE, inside=ARRIVAL)
    village.doors.append(door)
    plan.doors.append(door)
    village.piece("metro_entrance", ENTRANCE.x - 1, ENTRANCE.y - 2, 1, 3)
    return [plan, *floors]
