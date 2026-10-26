"""The sewers under the metro: a pool of seeded levels, of which each world plays one."""

import random
from collections import deque
from collections.abc import Iterator
from dataclasses import dataclass, field

from simile.schema import (
    Bionic,
    Door,
    DoorKind,
    InteractableKind,
    Item,
    ItemKind,
    MapTile,
    Tile,
    TileArea,
)
from simile.street.jump import KITS, OWN_JUMP, Jump, meets
from simile.street.metro import LIFT_FOOT, METRO, SALVAGE, SECRET, light, machine
from simile.street.moves import moves
from simile.street.plan import Pickup, Plan
from simile.street.village import GROUND, plug, street

SEWERS = "sewers"
LEVELS = 8
"""How many levels `simile street` writes to content/street/levels/."""
LANDING = MapTile(map=SEWERS, x=2, y=GROUND)
"""Where the lift from the metro stops."""
SHAFT = 12
"""The lift's landing is the first 12 cells, S8's, so a position saved there still stands."""
APEX_ACTUATOR = Item(id="apex_actuator", kind=ItemKind.PART, name="Apex actuator", weight=2.0)
"""The part premium legs need, from Apex's own stock, on a pipe past every level's gate."""
HATCH = "sewers_hatch"
"""The maintenance hatch deep in every level, a jack holding Aris's trail."""
FLOORS = (GROUND, GROUND - 5, GROUND - 10)
"""Each tier's standing row, bottom up, with four rows of room over it."""
CEILING = FLOORS[-1] - 4
"""The vault's lowest row: it's solid from the top of the map down to it."""
GATE = 17
"""The gate hall's width: the way on from the lift, across its gap on the legs or over its weir on
the feet."""
GAP = 5
"""Open cells in the gate's high gap and the legs' pocket's, a jump of six: the bionic legs'."""
WEIR = 3
"""Rows up the gate's weir is: out of reach of the bionic legs, in the spring feet's."""
WEIR_AT = 12
"""Cells into the gate hall: farther than a fall from its west walkway carries anyone."""
ATTEMPTS = 40

ROOMS, HALL, SHAFT_KIND, GATE_KIND = "rooms", "hall", "shaft", "gate"
SPRING_SECRET = "sewers_secret_spring"
SPRINT_SECRET = "sewers_secret_sprint"
ACTUATOR_SECRET = "sewers_secret_actuator"
PIPE_SECRET = "sewers_secret_pipe"

type Cell = tuple[int, int]
type Node = tuple[int, int]
"""A room: its column's index and its tier. A hall's tier 2 is the walkway over it."""


def scrap(item_id: str, name: str, weight: float) -> Item:
    return Item(id=item_id, kind=ItemKind.SALVAGE, name=name, weight=weight)


SALVAGE_ITEMS = (
    scrap("lead_pipe", "Lead pipe", 3.0),
    scrap("copper_coil", "Copper coil", 1.0),
    scrap("brass_fitting", "Brass fitting", 0.8),
    scrap("pump_impeller", "Pump impeller", 2.5),
    scrap("float_valve", "Float valve", 1.2),
    scrap("filter_mesh", "Filter mesh", 1.5),
    scrap("old_battery", "Old battery", 2.0),
)
"""What lies on the way through. `simile.economy` prices each."""
APEX_BOARD = scrap("apex_board", "Apex control board", 0.4)
GAUGE = scrap("pressure_gauge", "Pressure gauge", 0.6)


def slab(tier: int) -> int:
    """The solid row a tier stands on."""
    return FLOORS[tier] + 1


@dataclass
class Column:
    kind: str
    x: int
    width: int
    zone: int
    """0 between the lift and the gate, 1 past it."""

    @property
    def end(self) -> int:
        """The wall cell east of it, or the map's edge."""
        return self.x + self.width


@dataclass(frozen=True)
class Edge:
    kind: str
    """`door`, through the wall east of column `c` on tier `t`, or `ladder`, up from (c, t)."""
    c: int
    t: int


@dataclass
class Level:
    """A level's rooms and how they join, before it's carved into a plan."""

    seed: int
    rng: random.Random
    columns: list[Column] = field(default_factory=list)
    doors: set[tuple[int, int]] = field(default_factory=set)
    ladders: dict[Node, int] = field(default_factory=dict)
    openings: dict[Node, int] = field(default_factory=dict)
    """The open cell beside each ladder's top, so a walk along that floor ends at the ladder."""
    drops: dict[Node, int] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    """The doors and ladders every room is joined by, walking and climbing."""
    spring_pocket: int = 0
    """The column whose top room only a drop from the room under it joins."""
    reserved: dict[int, set[int]] = field(default_factory=dict)

    @property
    def gate(self) -> int:
        return next(i for i, c in enumerate(self.columns) if c.kind == GATE_KIND)

    @property
    def width(self) -> int:
        return self.columns[-1].end

    def nodes(self, zone: int) -> list[Node]:
        found = []
        for i, column in enumerate(self.columns):
            if column.zone == zone and column.kind != GATE_KIND:
                tiers = {SHAFT_KIND: (0,), ROOMS: (0, 1, 2), HALL: (0, 2)}[column.kind]
                found += [(i, t) for t in tiers if (i, t) != (self.spring_pocket, 2)]
        return found

    def ends(self, edge: Edge) -> tuple[Node, Node]:
        if edge.kind == "door":
            return (edge.c, edge.t), (edge.c + 1, edge.t)
        return (edge.c, edge.t), (edge.c, edge.t + 1)


def layout(seed: int, attempt: int = 0) -> Level:
    """A level's columns, and each zone's rooms joined by doors, ladders and a drop or two."""
    level = Level(seed, random.Random(f"sewers/{seed}/{attempt}"))
    rng = level.rng
    west = [ROOMS] * rng.choice((2, 3))
    east = [ROOMS] * rng.choice((3, 4))
    if len(west) == 3 and rng.random() < 0.5:
        west[1] = HALL
    else:
        east[rng.randrange(1, len(east))] = HALL
    kinds = [(SHAFT_KIND, 0), *((k, 0) for k in west), (GATE_KIND, 0), *((k, 1) for k in east)]
    x = 0
    for kind, zone in kinds:
        width = {SHAFT_KIND: SHAFT, GATE_KIND: GATE}.get(kind) or rng.randint(
            *((10, 12) if kind == HALL else (11, 14))
        )
        level.columns.append(Column(kind, x, width, zone))
        x += width + 1
    gate, hall = level.gate, next(i for i, c in enumerate(level.columns) if c.kind == HALL)
    level.spring_pocket = rng.choice(
        [
            i
            for i, c in enumerate(level.columns)
            if c.kind == ROOMS and abs(i - gate) > 1 and i != hall - 1
        ]
    )
    for zone in (0, 1):
        join(level, zone)
    level.doors |= {(gate - 1, 0), (gate - 1, 2), (gate, 0), (gate, 2)}
    return level


def join(level: Level, zone: int) -> None:
    """A random tree of doors and ladders over the zone's rooms, then an extra door and drops."""
    rng, columns = level.rng, level.columns
    nodes = level.nodes(zone)
    here = set(nodes)
    candidates = []
    for c, t in nodes:
        kind = columns[c].kind
        if (c + 1, t) in here and not (kind == HALL and t == 2):
            candidates.append(Edge("door", c, t))
        if kind == ROOMS and t < 2 and (c, t + 1) in here:
            candidates.append(Edge("ladder", c, t))
    weights = {e: rng.random() * (1.8 if (e.kind, e.t) == ("door", 0) else 1.0) for e in candidates}
    parent = {node: node for node in nodes}

    def find(node: Node) -> Node:
        while parent[node] != node:
            node = parent[node]
        return node

    chosen, rest = [], []
    for edge in sorted(candidates, key=weights.__getitem__):
        a, b = (find(n) for n in level.ends(edge))
        if a == b:
            rest.append(edge)
        else:
            parent[a] = b
            chosen.append(edge)
    if len({find(n) for n in nodes}) != 1:
        raise ValueError(f"zone {zone} of sewers level {level.seed} isn't joined up")
    doors = [edge for edge in rest if edge.kind == "door"]
    if doors and rng.random() < 0.6:
        chosen.append(rng.choice(doors))
    level.edges += chosen
    level.doors |= {(e.c, e.t) for e in chosen if e.kind == "door"}
    level.ladders |= {(e.c, e.t): -1 for e in chosen if e.kind == "ladder"}
    drops = [e for e in rest if e.kind == "ladder" and columns[e.c].kind == ROOMS]
    for edge in rng.sample(drops, min(len(drops), rng.randint(1, 2))):
        level.drops[(edge.c, edge.t)] = -1
    if columns[level.spring_pocket].zone == zone:
        level.drops[(level.spring_pocket, 1)] = -1


def walls(level: Level, node: Node) -> Iterator[int]:
    """Where a pipe two cells long fits against a wall of a room: at its first cell, or its last."""
    c, tier = node
    column = level.columns[c]
    if (c - 1, tier) not in level.doors:
        yield column.x
    if (c, tier) not in level.doors and column.end < level.width:
        yield column.end - 2


def shelves(level: Level) -> list[tuple[Node, int]]:
    """A pipe two rows up on a wall: past the gate for the actuator, and before it in most."""
    rng = level.rng
    found = []
    for zone in (1, 0):
        spots = [
            (node, x)
            for node in level.nodes(zone)
            if level.columns[node[0]].kind == ROOMS and node[0] != level.spring_pocket
            for x in walls(level, node)
        ]
        if not spots and zone == 1:
            raise ValueError(f"no wall past the gate for the actuator in level {level.seed}")
        if spots and (zone == 1 or rng.random() < 0.7):
            node, x = rng.choice(spots)
            level.reserved.setdefault(node[0], set()).update(range(x - 1, x + 3))
            found.append((node, x))
    return found


def place_holes(level: Level) -> None:
    """Where each two-cell hole goes through its slab, apart, with floor past each ladder's top."""
    rng = level.rng
    for i, column in enumerate(level.columns):
        reserved, used = level.reserved.get(i, set()), set()
        for node in sorted(k for k in [*level.ladders, *level.drops] if k[0] == i):
            ladder = node in level.ladders
            spots = [
                (x, side)
                for x in range(column.x + 1, column.end - 2)
                for side in ((0, 1) if ladder else (0,))
                if not {x, x + 1} & reserved
                and all(abs(x + d - u) >= 4 for d in (0, 1) for u in used)
                and not (ladder and room(column, x + side, side) < 3)
            ]
            if not spots:
                raise ValueError(f"no room for a hole in column {i} of sewers level {level.seed}")
            x, side = rng.choice(spots)
            used |= {x, x + 1}
            if ladder:
                level.ladders[node], level.openings[node] = x + side, x + 1 - side
            else:
                level.drops[node] = x


def room(column: Column, ladder: int, side: int) -> int:
    """Cells of floor past a ladder's top, on the side away from its opening, to the wall."""
    return column.end - 1 - ladder if side else ladder - column.x


def carve(level: Level, plan: Plan) -> None:
    """The ceiling, each tier's slabs, the walls between the columns, the gate, and the holes."""
    plan.fill(0, 0, level.width, CEILING + 1)
    for i, column in enumerate(level.columns):
        x, width = column.x, column.width
        if column.kind == ROOMS:
            for tier in (1, 2):
                plan.fill(x, slab(tier), width, 1)
        elif column.kind == HALL:
            plan.fill(x, slab(2), width - GAP - 2, 1)
            plan.fill(column.end - 2, slab(2), 2, 1)
        elif column.kind == GATE_KIND:
            plan.fill(x, slab(2), 3, 1)
            plan.fill(x + 3 + GAP, slab(2), width - 3 - GAP, 1)
            plan.fill(x + WEIR_AT, GROUND + 1 - WEIR, 2, WEIR)
        if column.end < level.width:
            plan.fill(column.end, slab(1), 1, 1)
            plan.fill(column.end, slab(2), 1, 1)
            for tier in range(3):
                if (i, tier) not in level.doors:
                    plan.fill(column.end, FLOORS[tier] - 3, 1, 4)
    for (_, tier), x in level.drops.items():
        plan.clear(x, slab(tier + 1), 2, 1)
    for (c, tier), x in level.ladders.items():
        plan.clear(min(x, level.openings[(c, tier)]), slab(tier + 1), 2, 1)
        plan.ladder((x, FLOORS[tier]), FLOORS[tier] - FLOORS[tier + 1])


class Stocker:
    """Picks free cells along the rooms' floors for what's put in them."""

    def __init__(self, level: Level, plan: Plan) -> None:
        self.level, self.plan = level, plan
        self.taken: set[Cell] = {(LANDING.x, GROUND), (LANDING.x + 1, GROUND)}

    def free(self, node: Node, width: int = 1) -> list[int]:
        c, tier = node
        column, row = self.level.columns[c], FLOORS[tier]
        foot = self.level.ladders.get(node)
        last = column.end - (1 if column.kind == SHAFT_KIND else 0)
        if column.kind == HALL and tier == 2:
            last = column.end - GAP - 2

        def ok(x: int) -> bool:
            standing = self.plan.standing(x, row) and (x, row) not in self.taken
            return standing and x != foot and column.x <= x < last

        return [x for x in range(column.x, last) if all(ok(x + d) for d in range(width))]

    def take(self, node: Node, width: int = 1, at: str = "any") -> Cell | None:
        xs = self.free(node, width)
        if not xs:
            return None
        x = {"any": self.level.rng.choice, "west": min, "east": max}[at](xs)
        row = FLOORS[node[1]]
        self.taken |= {(x + d, row) for d in range(-1, width + 1)}
        return x, row


def stock(level: Level, plan: Plan, shelves: list[tuple[Node, int]]) -> None:
    """The hatch, the plugs, the secrets and the salvage."""
    rng, gate, cells = level.rng, level.gate, Stocker(level, plan)
    west, east = level.nodes(0), level.nodes(1)
    room = farthest(level, (gate + 1, 0))
    at = "east" if room[0] == len(level.columns) - 1 else rng.choice(("west", "east"))
    hatch = cells.take(room, 2, at)
    if hatch is None:
        raise ValueError(f"no room for the hatch in sewers level {level.seed}")
    hx, hy = hatch
    area = TileArea(x=hx, y=hy - 1, width=2, height=2)
    machine(plan, HATCH, "Maintenance hatch", area, [Tile(x=hx, y=hy)], InteractableKind.JACK)
    plan.piece("maintenance_hatch", hx, hy - 1, 2, 2)
    plugs = [rng.choice([n for n in west if n[0] == gate - 1])]
    if rng.random() < 0.5:
        plugs.append(rng.choice([n for n in east if n != room]))
    for number, node in enumerate(plugs, 1):
        spot = cells.take(node)
        if spot is None:
            raise ValueError(f"no room for a plug in sewers level {level.seed}")
        px, py = spot
        plug_id = f"sewers_plug_{number}"
        area = TileArea(x=px, y=py - 1, width=1, height=2)
        plug(plan, plug_id, "Junction box", area, Tile(x=px, y=py))
        plan.piece("breaker_box", px, py - 1, 1, 2)
        left, right = max(px - 1, 0), min(px + 2, level.width)
        light(plan, plug_id, left, FLOORS[node[1]] - 3, right - left, 4, lit=True)
    pockets(level, plan)
    for (node, x), zone in zip(shelves, (1, 0), strict=False):
        row = FLOORS[node[1]] - 2
        plan.fill(x, row + 1, 2, 1)
        plan.piece("sewer_pipe", x, row + 1, 2, 1)
        end = x if x == level.columns[node[0]].x else x + 1
        if zone == 1:
            secret = Pickup(ACTUATOR_SECRET, SECRET, end, row, item=APEX_ACTUATOR, needs=OWN_JUMP)
        else:
            money = float(rng.choice((20, 25, 30, 35, 40)))
            secret = Pickup(PIPE_SECRET, SECRET, end, row, money, needs=OWN_JUMP)
        plan.pickups.append(secret)
    rooms = [n for n in west if n != (0, 0)], east
    spread = [*rng.sample(rooms[0], 2), *rng.sample(rooms[1], 4)]
    items = rng.sample(SALVAGE_ITEMS, len(spread))
    for number, (node, item) in enumerate(zip(spread, items, strict=True), 1):
        spot = cells.take(node)
        if spot is not None:
            plan.pickups.append(Pickup(f"sewers_salvage_{number}", SALVAGE, *spot, item=item))
    dress(level, plan, cells, [*rooms[0], *rooms[1]], room)


def pockets(level: Level, plan: Plan) -> None:
    """The secrets only a grade reaches: the spring pocket's room on the feet, and on the legs
    the hall's ledge."""
    rng = level.rng
    column = level.columns[level.spring_pocket]
    hole = level.drops[(level.spring_pocket, 1)]
    far = column.x if hole - column.x > column.end - hole else column.end - 1
    near = far + (1 if far == column.x else -1)
    row = FLOORS[2]
    spring, sprint = Bionic.SPRING_FEET_2, Bionic.BIONIC_LEGS
    money = float(rng.choice((60, 70, 80, 90)))
    plan.pickups.append(Pickup(SPRING_SECRET, SECRET, far, row, money, needs=spring))
    salvage = Pickup("sewers_salvage_spring", SALVAGE, near, row, item=GAUGE, needs=spring)
    plan.pickups.append(salvage)
    hall = next(c for c in level.columns if c.kind == HALL)
    money = float(rng.choice((50, 60, 70, 80)))
    end = hall.end - 1
    plan.pickups.append(Pickup(SPRINT_SECRET, SECRET, end, row, money, needs=sprint))
    salvage = Pickup("sewers_salvage_sprint", SALVAGE, end - 1, row, item=APEX_BOARD, needs=sprint)
    plan.pickups.append(salvage)


def farthest(level: Level, start: Node) -> Node:
    """The room the most doors and ladders from `start`."""
    near: dict[Node, list[Node]] = {}
    for edge in level.edges:
        a, b = level.ends(edge)
        near.setdefault(a, []).append(b)
        near.setdefault(b, []).append(a)
    seen, queue, last = {start}, deque([start]), start
    while queue:
        last = queue.popleft()
        for there in near.get(last, []):
            if there not in seen:
                seen.add(there)
                queue.append(there)
    return last


DECOR = (("rubble", 2), ("crates", 1), ("bedroll", 2), ("sewer_outfall", 2))


def dress(level: Level, plan: Plan, cells: Stocker, rooms: list[Node], hatch: Node) -> None:
    """Junk on the floors, pipes along the walls, and a lamp lighting some rooms."""
    rng = level.rng
    plan.piece("pipes", 0, GROUND - 3, SHAFT, 1)
    plan.piece("rubble", 7, GROUND, 2, 1)
    for number, node in enumerate(rooms, 1):
        column, row = level.columns[node[0]], FLOORS[node[1]]
        if rng.random() < 0.6:
            name, width = rng.choice(DECOR)
            spot = cells.take(node, width)
            if spot is not None:
                tall = name == "sewer_outfall"
                plan.piece(name, spot[0], row - tall, width, 1 + tall)
        if rng.random() < 0.35:
            plan.piece("pipes", column.x, row - 2, column.width, 1)
        if node != hatch and rng.random() < 0.25:
            middle = column.x + column.width // 2
            plan.piece("sewer_lamp", middle, row - 3, 1, 1)
            light(plan, f"sewers_lamp_{number}", column.x, row - 3, column.width, 4, lit=True)


def cover(level: Level, plan: Plan) -> None:
    """A piece over everything solid above the floor, so no plain ledge shows."""
    plan.piece("sewer_vault", 0, 0, level.width, CEILING + 1)
    for row in (slab(1), slab(2)):
        x = 0
        while x < level.width:
            if (x, row) not in plan.solid:
                x += 1
                continue
            start = x
            while (x, row) in plan.solid:
                x += 1
            if x - start >= 3:
                plan.piece("sewer_walkway", start, row - 1, x - start, 2)
            else:
                plan.piece("sewer_pipe", start, row, x - start, 1)
    for i, column in enumerate(level.columns[:-1]):
        for tier in range(3):
            if (i, tier) not in level.doors:
                plan.piece("sewer_pier", column.end, FLOORS[tier] - 3, 1, 4)
    gate = level.columns[level.gate]
    plan.piece("sewer_weir", gate.x + WEIR_AT, GROUND + 1 - WEIR, 2, WEIR + 2)
    for x in (gate.x + 5, gate.x + WEIR_AT - 3):
        plan.piece("sewer_lamp", x, FLOORS[1] - 1, 1, 1)


def lift() -> Door:
    """The metro's maintenance lift, down to every level's landing."""
    return Door(id=f"{METRO}_to_{SEWERS}", outside=LIFT_FOOT, inside=LANDING)


def build(level: Level) -> Plan:
    plan = street(SEWERS, "The Sewers", level.width)
    ledges = shelves(level)
    place_holes(level)
    carve(level, plan)
    light(plan, "sewers_dark", 0, 0, level.width, plan.height, lit=False)
    light(plan, "sewers_landing", 0, 0, SHAFT, plan.height, lit=True)
    gate = level.columns[level.gate]
    light(plan, "sewers_gate", gate.x, CEILING + 1, gate.width, GROUND - CEILING, lit=True)
    plan.piece("freight_lift", LANDING.x, GROUND - 3, 2, 4)
    stock(level, plan, ledges)
    cover(level, plan)
    plan.doors.append(lift())
    return plan


def sewers(seed: int) -> Plan:
    """The level for `seed`: the first of its layouts that `problems` finds nothing wrong with."""
    found: list[str] = []
    for attempt in range(ATTEMPTS):
        try:
            plan = build(layout(seed, attempt))
            plan.check()
        except ValueError as error:
            found = [str(error)]
            continue
        found = problems(plan)
        if not found:
            return plan
    raise ValueError(f"no sewers level for seed {seed}: {'; '.join(found)}")


def levels() -> list[Plan]:
    """Every level, level `n` from seed `n`, each joined to the metro by its lift."""
    return [sewers(seed) for seed in range(LEVELS)]


class Cells:
    """A plan read as `moves` reads a map."""

    def __init__(self, plan: Plan) -> None:
        self.plan, self.width, self.height = plan, plan.width, plan.height

    def solid(self, x: int, y: int) -> bool:
        return not (0 <= x < self.width and 0 <= y < self.height) or (x, y) in self.plan.solid

    def climb(self, x: int, y: int) -> DoorKind | None:
        return self.plan.climbable.get((x, y))

    def walkable(self, x: int, y: int) -> bool:
        return self.plan.walkable(x, y)

    def standing(self, x: int, y: int) -> bool:
        return self.plan.standing(x, y)


def routes(town: object, start: Cell, jump: bool | Jump) -> dict[Cell, list[Cell]]:
    """Every cell the player gets to from `start` on `jump`, or walking and climbing alone, with the
    cells a move takes them to from each."""
    found: dict[Cell, list[Cell]] = {}
    queue = deque([start])
    while queue:
        cell = queue.popleft()
        if cell in found:
            continue
        found[cell] = [there for there, _ in moves(town, cell, jump)]
        queue.extend(there for there in found[cell] if there not in found)
    return found


def stranded(ways: dict[Cell, list[Cell]], start: Cell) -> set[Cell]:
    """Of the cells in `ways`, from `routes`, those the player can't get back to `start` from."""
    into: dict[Cell, list[Cell]] = {}
    for cell, theres in ways.items():
        for there in theres:
            into.setdefault(there, []).append(cell)
    seen, queue = {start}, deque([start])
    while queue:
        for there in into.get(queue.popleft(), []):
            if there not in seen:
                seen.add(there)
                queue.append(there)
    return set(ways) - seen


def problems(plan: Plan, town: object | None = None) -> list[str]:
    """Where a level fails content/street/README.md's checks for the sewers: none if it's sound."""
    town = town or Cells(plan)
    start = (LANDING.x, LANDING.y)
    found: list[str] = []
    by_jump: dict[Jump, set[Cell]] = {}
    for name, jump in KITS.items():
        if jump in by_jump:
            continue
        ways = routes(town, start, jump)
        by_jump[jump] = set(ways)
        if stuck := stranded(ways, start):
            found.append(f"{name} can't get back to the lift from {min(stuck)}")
    reached = {name: by_jump[jump] for name, jump in KITS.items()}
    [hatch] = [item for item in plan.interactables if item.id == HATCH]
    plugs = [item for item in plan.interactables if item.kind is InteractableKind.PLUG]
    for item in [hatch, *plugs]:
        cell = (item.stand[0].x, item.stand[0].y)
        missed = [name for name in KITS if name != OWN_JUMP and cell not in reached[name]]
        if missed:
            found.append(f"{item.id} is out of reach of {', '.join(missed)}")
    if (hatch.stand[0].x, hatch.stand[0].y) in reached[OWN_JUMP]:
        found.append("the hatch is in reach of the player's own legs")
    for pickup in plan.pickups:
        cell = (pickup.x, pickup.y)
        for name, jump in KITS.items():
            reaches = cell in reached[name]
            if name != OWN_JUMP and reaches != meets(jump, pickup.needs or OWN_JUMP):
                found.append(f"{pickup.id} needs {pickup.needs}, but {name} says otherwise")
        if pickup.needs not in (None, OWN_JUMP) and cell in reached[OWN_JUMP]:
            found.append(f"{pickup.id} is in reach of the player's own legs")
    return found
