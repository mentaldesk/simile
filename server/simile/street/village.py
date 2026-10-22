from collections.abc import Sequence

from simile.schema import (
    Door,
    DoorKind,
    Facing,
    Interactable,
    InteractableKind,
    Location,
    LocationKind,
    MapArea,
    MapTile,
    Tile,
    TileArea,
)
from simile.street.plan import Facade, Plan
from simile.world.map import MapKind, MuralWall, SpotKind

GROUND = 15
"""Each street's standing row, with solid ground under it."""
STREET_HEIGHT = 20
STOREY = 4
"""A floor map's height: three rows of room over a row of floor."""
FLOOR_ROW = STOREY - 2
"""A floor's standing row."""
STOOL_M = 0.25
"""How much higher a stool's seat is than a chair's."""
JUMPING = frozenset({"rooftops", "metro"})
"""Streets only the player gets all over, by jumping. No resident goes there."""
UNDERGROUND = frozenset({"metro"})
"""Streets under the village."""

N, E, W = Facing.NORTH, Facing.EAST, Facing.WEST
SEAT, BAR, DESK, VIEWING = SpotKind.SEAT, SpotKind.BAR, SpotKind.DESK, SpotKind.VIEWING
FRAMES = [(3, 0), (7, 0), (11, 0), (15, 0), (19, 0), (23, 0), (27, 0)]
FRAMES += [(5, 9), (8, 9), (11, 9), (19, 9), (22, 9), (25, 9)]
"""Each gallery painting's frame on today's map, which its viewing spots are named after."""


def street(map_id: str, label: str, width: int) -> Plan:
    plan = Plan(map_id, width, STREET_HEIGHT, MapKind.STREET, label=label)
    plan.fill(0, GROUND + 1, width, STREET_HEIGHT - GROUND - 1)
    return plan


def front(x: int, width: int, storeys: int) -> TileArea:
    """A building's storeys on its street, down to the street's standing row."""
    top = GROUND - FLOOR_ROW - STOREY * (storeys - 1)
    return TileArea(x=x, y=top, width=width, height=GROUND + 1 - top)


class Building:
    """A location's building on a street, a floor map for each storey, each a room whose
    standing row is level with the street's on the ground floor."""

    def __init__(
        self,
        street: Plan,
        location_id: str,
        label: str,
        kind: LocationKind,
        x: int,
        width: int,
        rooms: Sequence[str],
    ) -> None:
        self.street, self.id, self.label, self.kind, self.x = street, location_id, label, kind, x
        self.floors = [self._floor(n, room, width) for n, room in enumerate(rooms)]
        area = front(x, width, len(rooms))
        street.buildings.append(Facade(location_id, label, area, len(rooms), interior=True))

    def _floor(self, number: int, room: str, width: int) -> Plan:
        plan = Plan(
            f"{self.id}_floor_{number}",
            width,
            STOREY,
            MapKind.FLOOR,
            building=self.id,
            floor=number,
            room=room,
            street=self.street.id,
            street_x=self.x,
            street_y=GROUND - FLOOR_ROW - STOREY * number,
        )
        plan.fill(0, STOREY - 1, width, 1)
        plan.fill(0, 0, 1, STOREY - 1)
        plan.fill(width - 1, 0, 1, STOREY - 1)
        return plan

    @property
    def room(self) -> TileArea:
        return TileArea(x=1, y=0, width=self.floors[0].width - 2, height=FLOOR_ROW + 1)

    def door(self, x: int) -> None:
        """The front door, from the street to the mat at `x` on the ground floor."""
        street_end = MapTile(map=self.street.id, x=self.x + x, y=GROUND)
        mat = MapTile(map=self.floors[0].id, x=x, y=FLOOR_ROW)
        _add(Door(id=self.id, outside=street_end, inside=mat), self.street, self.floors[0])

    def link(
        self, link_id: str, kind: DoorKind, lower: tuple[int, int], upper: tuple[int, int]
    ) -> None:
        """Stairs, a ladder or a lift from (floor, x) to (floor, x) above it."""
        (low, low_x), (high, high_x) = lower, upper
        outside = MapTile(map=self.floors[low].id, x=low_x, y=FLOOR_ROW)
        inside = MapTile(map=self.floors[high].id, x=high_x, y=FLOOR_ROW)
        door = Door(id=link_id, kind=kind, outside=outside, inside=inside)
        _add(door, self.floors[low], self.floors[high])

    def place(self, entry: int) -> None:
        room = self.room.model_dump()
        location = Location(
            id=self.id,
            name=self.label,
            kind=self.kind,
            map=self.floors[0].id,
            area=self.room,
            entry=Tile(x=entry, y=FLOOR_ROW),
            floors=[MapArea(map=floor.id, **room) for floor in self.floors[1:]],
        )
        self.floors[0].locations.append(location)


def _add(door: Door, *plans: Plan) -> None:
    for plan in plans:
        plan.doors.append(door)


def join(a: Plan, a_x: int, b: Plan, b_x: int) -> None:
    """A door between two streets, outside on the one whose id comes first."""
    (outside, out_x), (inside, in_x) = sorted(((a, a_x), (b, b_x)), key=lambda end: end[0].id)
    door = Door(
        id=f"{outside.id}_to_{inside.id}",
        outside=MapTile(map=outside.id, x=out_x, y=GROUND),
        inside=MapTile(map=inside.id, x=in_x, y=GROUND),
    )
    _add(door, outside, inside)


def scenery(street: Plan, building_id: str, label: str, x: int, width: int, storeys: int) -> None:
    """A building with no way in, drawn on the street."""
    area = front(x, width, storeys)
    street.buildings.append(Facade(building_id, label, area, storeys, interior=False))


def mural(
    street: Plan, wall_id: str, x: int, width: int, bottom: float, top: float, spot_id: str
) -> None:
    """A wall facing the camera from `x` along the street, with its painter in the middle."""
    stand = Tile(x=x + width // 2, y=GROUND)
    street.murals.append(MuralWall(wall_id, x, GROUND, width, "south", bottom, top, stand))
    street.spot(spot_id, VIEWING, stand.x, stand.y, N)


def terminal(
    street: Plan, number: int, label: str, x: int, spot_id: str, row: int = GROUND
) -> None:
    area = TileArea(x=x, y=row - 2, width=1, height=3)
    kind = LocationKind.TERMINAL
    location = Location(
        id=f"terminal_{number}",
        name=label,
        kind=kind,
        map=street.id,
        area=area,
        entry=Tile(x=x, y=row),
    )
    street.locations.append(location)
    street.spot(spot_id, SpotKind.TERMINAL, x, row, N)
    street.piece("news_terminal", x, row - 1, 1, 2)


def bench(plan: Plan, x: int, row: int, facings: Sequence[Facing], *spot_ids: str) -> None:
    """Two seats, each facing what its sitter looks at."""
    plan.piece("bench", x, row, 2, 1)
    for i, (spot_id, facing) in enumerate(zip(spot_ids, facings, strict=True)):
        plan.spot(spot_id, SEAT, x + i, row, facing)


def stools(plan: Plan, x: int, kind: SpotKind, facing: Facing, *spot_ids: str) -> None:
    """A stool on each cell from `x` east, facing where the counter's served from."""
    for i, spot_id in enumerate(spot_ids):
        plan.piece("stool", x + i, FLOOR_ROW)
        plan.spot(spot_id, kind, x + i, FLOOR_ROW, facing, dz=STOOL_M)


def table(plan: Plan, name: str, x: int, old: tuple[int, int]) -> None:
    """A table with a chair either side facing it, keeping the seat ids of today's table at
    `old`, whose chairs were west and east of it."""
    old_x, old_y = old
    plan.piece(name, x, FLOOR_ROW, 2, 1)
    plan.spot(f"seat-{old_x - 1}-{old_y}", SEAT, x, FLOOR_ROW, E)
    plan.spot(f"seat-{old_x + 1}-{old_y}", SEAT, x + 1, FLOOR_ROW, W)


def workbench(plan: Plan, x: int, old: tuple[int, int]) -> None:
    """A bench along the back wall with four desks in front, keeping the desk ids of today's
    workbench at `old`, worked from both long sides."""
    old_x, old_y = old
    plan.piece("workbench", x, FLOOR_ROW, 4, 1)
    ids = [f"desk-{old_x + i}-{old_y + dy}" for dy in (-1, 1) for i in (0, 1)]
    for i, spot_id in enumerate(ids):
        plan.spot(spot_id, DESK, x + i, FLOOR_ROW, N)


def machine(plan: Plan, item_id: str, label: str, x: int, width: int, *desk_ids: str) -> None:
    area = TileArea(x=x, y=FLOOR_ROW - 1, width=width, height=2)
    stand = [Tile(x=x + i, y=FLOOR_ROW) for i in range(width)]
    kind = InteractableKind.MACHINE
    plan.interactables.append(
        Interactable(id=item_id, label=label, kind=kind, map=plan.id, area=area, stand=stand)
    )
    plan.piece(item_id, x, FLOOR_ROW - 1, width, 2)
    for tile, spot_id in zip(stand, desk_ids, strict=True):
        plan.spot(spot_id, DESK, tile.x, tile.y, N)


def painting(plan: Plan, number: int, x: int) -> None:
    """A frame at head height over the two cells it's looked at from."""
    area = TileArea(x=x, y=FLOOR_ROW - 1, width=2, height=1)
    stand = [Tile(x=x, y=FLOOR_ROW), Tile(x=x + 1, y=FLOOR_ROW)]
    kind = InteractableKind.PAINTING
    plan.interactables.append(
        Interactable(
            id=f"painting_{number}",
            label="Painting",
            kind=kind,
            map=plan.id,
            area=area,
            stand=stand,
        )
    )
    old_x, old_y = FRAMES[number - 1]
    for i, tile in enumerate(stand):
        plan.spot(f"viewing-{old_x + i}-{old_y + 2}", VIEWING, tile.x, tile.y, N)


def house(street: Plan, number: int, label: str, x: int, door_west: bool) -> list[Plan]:
    """Two floors: a living room with the front door and the foot of the stairs, a step in from
    the far wall, and a bedroom."""
    home = Building(
        street, f"house_{number}", label, LocationKind.HOUSE, x, 7, ("living_room", "bedroom")
    )
    living, bedroom = home.floors
    mat, foot, top = (1, 4, 1) if door_west else (5, 2, 5)
    home.door(mat)
    home.link(f"house_{number}_stairs", DoorKind.STAIRS, (0, foot), (1, top))
    home.place(entry=3)
    living.piece("kitchen", 5 if door_west else 1, FLOOR_ROW - 1, 1, 2)
    living.piece("sofa", 2 if door_west else 3, FLOOR_ROW, 2, 1)
    bedroom.piece("bed", 2 if door_west else 3, FLOOR_ROW, 2, 1)
    bedroom.piece("wardrobe", 5 if door_west else 1, FLOOR_ROW - 1, 1, 2)
    return home.floors


def noodle_bar(street: Plan, x: int) -> list[Plan]:
    """The entry by the door, two tables, the stools at the counter and the kitchen behind it
    downstairs, and a dining room above."""
    kind = LocationKind.NOODLE_BAR
    rooms = ("noodle_bar", "dining_room")
    shop = Building(street, "noodle_bar", "Golden Bowl Noodles", kind, x, 17, rooms)
    ground, dining = shop.floors
    shop.door(2)
    shop.link("noodle_bar_stairs", DoorKind.STAIRS, (0, 3), (1, 7))
    shop.place(entry=1)
    for at, old in ((4, (4, 8)), (6, (4, 11))):
        table(ground, "noodle_table", at, old)
    ground.piece("noodle_counter", 8, FLOOR_ROW, 5, 1)
    stools(ground, 8, SEAT, E, *(f"seat-{old_x}-5" for old_x in range(3, 13, 2)))
    ground.piece("kitchen_counter", 13, FLOOR_ROW)
    ground.piece("stove", 14, FLOOR_ROW - 1, 2, 2)
    upstairs = [(1, (8, 8)), (3, (8, 11)), (5, (12, 8)), (8, (12, 11)), (10, (16, 8))]
    upstairs += [(12, (16, 11)), (14, (16, 3))]
    for at, old in upstairs:
        table(dining, "noodle_table", at, old)
    return shop.floors


def coffee_shop(street: Plan, x: int) -> list[Plan]:
    """The counter, the queue and a bar with stools downstairs, tables upstairs, and the barista's
    flat on top. Behind the counter, west to east: the grinder, the espresso machine, the till
    and the hand-over, then on the customers' side the pickup and the queue, running east."""
    kind = LocationKind.COFFEE_SHOP
    rooms = ("cafe", "cafe_upstairs", "flat")
    cafe = Building(street, "coffee_shop", "The Daily Grind", kind, x, 20, rooms)
    ground, upstairs, flat = cafe.floors
    cafe.door(18)
    cafe.link("coffee_shop_stairs", DoorKind.STAIRS, (0, 15), (1, 18))
    cafe.link("coffee_shop_flat_stairs", DoorKind.STAIRS, (1, 11), (2, 14))
    cafe.place(entry=6)
    amenity = LocationKind.AMENITY
    ground.locations += [
        Location(
            id="coffee_shop_staff",
            name="Behind the counter at the Daily Grind",
            kind=amenity,
            map=ground.id,
            area=TileArea(x=1, y=0, width=4, height=FLOOR_ROW + 1),
            entry=Tile(x=3, y=FLOOR_ROW),
        ),
        Location(
            id="coffee_shop_queue",
            name="The queue at the Daily Grind",
            kind=amenity,
            map=ground.id,
            area=TileArea(x=6, y=0, width=4, height=FLOOR_ROW + 1),
            entry=Tile(x=6, y=FLOOR_ROW),
        ),
    ]
    ground.interactables.append(
        Interactable(
            id="coffee_shop_counter",
            label="Counter",
            kind=InteractableKind.COUNTER,
            map=ground.id,
            area=TileArea(x=3, y=FLOOR_ROW, width=3, height=1),
            stand=[Tile(x=6, y=FLOOR_ROW)],
        )
    )
    ground.piece("grinder", 1, FLOOR_ROW)
    ground.piece("espresso_machine", 2, FLOOR_ROW)
    ground.piece("counter", 3, FLOOR_ROW, 3, 1)
    ground.piece("menu_board", 2, 0, 3, 1)
    ground.piece("bar_counter", 10, FLOOR_ROW, 5, 1)
    ground.piece("plant", 17, FLOOR_ROW)
    stools(ground, 10, BAR, W, "bar-2-6", "bar-3-6", "bar-10-3", "bar-10-4", "bar-10-5")
    tables = [(1, (2, 8)), (3, (2, 11)), (5, (12, 3)), (7, (15, 3)), (9, (12, 7))]
    tables += [(12, (15, 7)), (14, (12, 10)), (16, (15, 10))]
    for at, old in tables:
        table(upstairs, "cafe_table", at, old)
    flat.piece("bed", 1, FLOOR_ROW, 2, 1)
    flat.piece("wardrobe", 3, FLOOR_ROW - 1, 1, 2)
    flat.piece("sofa", 5, FLOOR_ROW, 2, 1)
    flat.piece("kitchen", 8, FLOOR_ROW - 1, 3, 2)
    flat.piece("table", 11, FLOOR_ROW, 2, 1)
    flat.piece("bookshelf", 17, FLOOR_ROW - 1, 1, 2)
    return cafe.floors


def maker_space(street: Plan, x: int) -> list[Plan]:
    """The machines and a workbench downstairs, three workbenches above, and a loft up a ladder
    with two more."""
    kind = LocationKind.MAKER_SPACE
    rooms = ("workshop", "workshop", "loft")
    shop = Building(street, "maker_space", "Spark Maker Space", kind, x, 16, rooms)
    ground, first, loft = shop.floors
    shop.door(14)
    shop.link("maker_space_stairs", DoorKind.STAIRS, (0, 2), (1, 5))
    shop.link("maker_space_ladder", DoorKind.LADDER, (1, 6), (2, 6))
    shop.place(entry=13)
    workbench(ground, 3, (3, 6))
    ground.piece("pegboard", 3, 0, 4, 1)
    machine(ground, "laser_cutter", "Laser cutter", 7, 2, "desk-2-3", "desk-3-3")
    machine(ground, "printer_3d", "3D printer", 9, 1, "desk-6-3")
    machine(ground, "loom", "Loom", 10, 2, "desk-10-3", "desk-11-3")
    machine(ground, "sewing_machine", "Sewing machine", 12, 1, "desk-15-3")
    for at, old in ((1, (3, 9)), (7, (8, 6)), (11, (8, 9))):
        workbench(first, at, old)
    for at, old in ((1, (13, 6)), (7, (13, 9))):
        workbench(loft, at, old)
    loft.piece("shelf", 11, FLOOR_ROW - 1, 4, 2)
    return shop.floors


def gallery(street: Plan, x: int) -> list[Plan]:
    """Three floors of paintings and benches, with a lift that stops at each."""
    kind = LocationKind.GALLERY
    rooms = ("gallery", "gallery", "gallery")
    building = Building(street, "gallery", "The Gallery", kind, x, 18, rooms)
    ground, first, top = building.floors
    building.door(2)
    building.link("gallery_lift_0_1", DoorKind.LIFT, (0, 16), (1, 16))
    building.link("gallery_lift_0_2", DoorKind.LIFT, (0, 15), (2, 16))
    building.link("gallery_lift_1_2", DoorKind.LIFT, (1, 15), (2, 15))
    building.place(entry=3)
    for plan in building.floors:
        plan.piece("lift", 15, 0, 2, FLOOR_ROW + 1)
    for number, at in ((1, 4), (2, 7), (3, 10)):
        painting(ground, number, at)
    bench(ground, 12, FLOOR_ROW, (W, W), "seat-8-4", "seat-9-4")
    for at in (6, 9):
        ground.piece("plinth", at, FLOOR_ROW)
    for number, at in ((4, 1), (5, 3), (6, 7), (7, 9), (8, 13)):
        painting(first, number, at)
    bench(first, 5, FLOOR_ROW, (W, E), "seat-22-4", "seat-23-4")
    bench(first, 11, FLOOR_ROW, (W, E), "seat-8-13", "seat-9-13")
    for number, at in ((9, 1), (10, 3), (11, 5), (12, 9), (13, 11)):
        painting(top, number, at)
    bench(top, 7, FLOOR_ROW, (W, E), "seat-22-13", "seat-23-13")
    top.piece("plinth", 13, FLOOR_ROW)
    return building.floors


def high_street() -> tuple[Plan, list[Plan]]:
    """The maker space, the corner shop, the Daily Grind and its terrace, the square, and the
    noodle bar. Kapok Walk and Lychee Lane lead off the square, and steps down to Banyan Row off
    its east end."""
    plan = street("high_street", "High Street", 84)
    floors = maker_space(plan, 2)
    scenery(plan, "corner_shop", "The corner shop", 19, 6, 3)
    mural(plan, "corner_shop", 20, 4, 0.7, 2.85, "viewing-22-8")
    floors += coffee_shop(plan, 25)
    mural(plan, "daily_grind", 27, 3, 1.05, 1.9, "viewing-29-11")
    terrace = TileArea(x=25, y=GROUND - 2, width=20, height=3)
    plan.locations.append(
        Location(
            id="cafe_terrace",
            name="The Daily Grind's terrace",
            kind=LocationKind.AMENITY,
            map=plan.id,
            area=terrace,
            entry=Tile(x=35, y=GROUND),
        )
    )
    for at in (31, 33, 38):
        plan.piece("cafe_table", at, GROUND)
    plan.piece("menu_board", 41, GROUND)
    square(plan)
    floors += noodle_bar(plan, 65)
    for at in (1, 82):
        plan.piece("lamp", at, GROUND - 2, 1, 3)
    return plan, floors


def square(plan: Plan) -> None:
    """The fountain, with benches and a lamp either side and the news terminal, and the doors to
    Kapok Walk (46), Lychee Lane (50) and Banyan Row (64)."""
    area = TileArea(x=45, y=GROUND - 2, width=20, height=3)
    plan.locations.append(
        Location(
            id="square",
            name="Town Square",
            kind=LocationKind.SQUARE,
            map=plan.id,
            area=area,
            entry=Tile(x=51, y=GROUND),
        )
    )
    terminal(plan, 1, "News terminal on the square", 60, "terminal-36-15")
    plan.piece("fountain", 55, GROUND - 1, 2, 2)
    for at in (47, 63):
        plan.piece("lamp", at, GROUND - 2, 1, 3)
    bench(plan, 48, GROUND, (E, E), "seat-27-19", "seat-28-19")
    bench(plan, 52, GROUND, (E, E), "seat-27-21", "seat-28-21")
    bench(plan, 58, GROUND, (W, W), "seat-34-19", "seat-35-19")
    bench(plan, 61, GROUND, (W, W), "seat-34-21", "seat-35-21")
    standing = [("standing-26-20", 47, E), ("standing-30-20", 54, E)]
    standing += [("standing-31-18", 55, N), ("standing-32-21", 56, N)]
    standing += [("standing-33-19", 57, W), ("standing-37-20", 63, W)]
    for spot_id, at, facing in standing:
        plan.spot(spot_id, SpotKind.STANDING, at, GROUND, facing)


def lychee_lane() -> tuple[Plan, list[Plan]]:
    """Four houses, the park gate's terminal, Lotus Lake Park with a lookout up a ladder, and the
    tower at the east end. The lane from the square comes in between 2 and 3 Lychee Lane."""
    plan = street("lychee_lane", "Lychee Lane", 68)
    floors = house(plan, 1, "1 Lychee Lane", 2, door_west=False)
    floors += house(plan, 2, "2 Lychee Lane", 9, door_west=True)
    floors += house(plan, 3, "3 Lychee Lane", 19, door_west=False)
    floors += house(plan, 4, "4 Lychee Lane", 26, door_west=True)
    terminal(plan, 2, "News terminal at the park gate", 34, "terminal-44-23")
    park = TileArea(x=36, y=GROUND - 4, width=24, height=5)
    plan.locations.append(
        Location(
            id="park",
            name="Lotus Lake Park",
            kind=LocationKind.AMENITY,
            map=plan.id,
            area=park,
            entry=Tile(x=37, y=GROUND),
        )
    )
    bench(plan, 39, GROUND, (E, E), "seat-49-27", "seat-50-27")
    bench(plan, 53, GROUND, (W, W), "seat-59-18", "seat-60-18")
    plan.ladder((45, GROUND), 3)
    plan.fill(46, GROUND - 2, 3, 1)
    for at in (42, 49, 57):
        plan.piece("tree", at, GROUND - 3, 2, 4)
    for at in (51, 59):
        plan.piece("bush", at, GROUND)
    plan.piece("lamp", 18, GROUND - 2, 1, 3)
    scenery(plan, "tower", "The tower", 61, 6, 3)
    mural(plan, "tower", 61, 5, 0.15, 3.0, "viewing-63-7")
    return plan, floors


def kapok_walk() -> tuple[Plan, list[Plan]]:
    """A garden at the west end and three houses, with the lane to the square at the east end."""
    plan = street("kapok_walk", "Kapok Walk", 34)
    plan.piece("bench", 3, GROUND, 2, 1)
    for at in (1, 6):
        plan.piece("tree", at, GROUND - 3, 2, 4)
    plan.piece("bush", 8, GROUND)
    floors = house(plan, 5, "1 Kapok Walk", 9, door_west=False)
    floors += house(plan, 6, "2 Kapok Walk", 16, door_west=True)
    floors += house(plan, 7, "3 Kapok Walk", 23, door_west=False)
    plan.piece("lamp", 31, GROUND - 2, 1, 3)
    return plan, floors


def banyan_row() -> tuple[Plan, list[Plan]]:
    """Three houses, the gallery and Garden Flats, then steps down to the river's promenade and
    its terminal. The steps up to the square are between 3 Banyan Row and the gallery."""
    plan = street("banyan_row", "Banyan Row", 68)
    floors = house(plan, 8, "1 Banyan Row", 2, door_west=False)
    floors += house(plan, 9, "2 Banyan Row", 9, door_west=True)
    floors += house(plan, 10, "3 Banyan Row", 16, door_west=True)
    mural(plan, "banyan_row", 19, 3, 0.15, 1.85, "viewing-18-32")
    floors += gallery(plan, 26)
    scenery(plan, "garden_flats", "Garden Flats", 45, 6, 3)
    mural(plan, "garden_flats", 45, 4, 0.15, 2.5, "viewing-34-31")
    river = GROUND + 3
    plan.clear(54, GROUND + 1, 14, 3)
    plan.stairs((56, river), east=False, steps=2)
    terminal(plan, 3, "News terminal by the river", 60, "terminal-46-37", row=river)
    for at in (57, 63):
        plan.piece("bench", at, river, 2, 1)
    for at in (59, 66):
        plan.piece("lamp", at, river - 2, 1, 3)
    return plan, floors


def rooftop(plan: Plan, building_id: str, label: str, x: int, width: int, storeys: int) -> int:
    """A building with a flat roof to stand on along its top row; returns the row stood on."""
    scenery(plan, building_id, label, x, width, storeys)
    top = front(x, width, storeys).y
    plan.fill(x, top, width, 1)
    return top - 1


def rooftops() -> Plan:
    """A lane behind Kapok Walk, and roofs over it to jump across: content/street/README.md."""
    plan = street("rooftops", "The Rooftops", 60)
    plan.ladder((3, GROUND), 3)
    bakery = rooftop(plan, "bakery", "The bakery", 4, 6, 1)
    plan.fill(11, bakery + 1, 2, 1)
    plan.fill(13, bakery - 1, 2, 1)
    roofs = rooftop(plan, "print_works", "The print works", 15, 7, 2)
    rooftop(plan, "tea_house", "The tea house", 24, 7, 2)
    rooftop(plan, "laundry", "The laundry", 34, 6, 2)
    plan.fill(40, roofs + 1, 8, 1)
    plan.piece("rope_bridge", 40, roofs, 8, 1)
    plan.fill(48, roofs + 1, 2, 1)
    top = rooftop(plan, "clock_house", "The clock house", 50, 7, 3)
    plan.ladder((49, roofs), roofs - top)
    plan.piece("palm_tree", 31, GROUND - 6, 2, 7)
    plan.piece("bench", 52, top, 2, 1)
    plan.piece("plant", 56, top)
    plan.piece("bicycle", 22, GROUND)
    plan.piece("bin", 13, GROUND)
    for at in (45, 58):
        plan.piece("lamp", at, GROUND - 2, 1, 3)
    return plan


def village() -> list[Plan]:
    """Every street, then every floor, with the streets joined."""
    from simile.street.metro import metro

    high, high_floors = high_street()
    lychee, lychee_floors = lychee_lane()
    kapok, kapok_floors = kapok_walk()
    banyan, banyan_floors = banyan_row()
    roofs = rooftops()
    join(high, 46, kapok, 32)
    join(high, 50, lychee, 17)
    join(high, 64, banyan, 24)
    join(kapok, 2, roofs, 1)
    below, *below_floors = metro(banyan)
    plans = [high, lychee, kapok, banyan, roofs, below, *high_floors, *lychee_floors]
    plans += [*kapok_floors, *banyan_floors, *below_floors]
    for plan in plans:
        plan.check()
    return plans
