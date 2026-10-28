"""The sewers under the metro: a pool of seeded levels, of which each world plays one."""

import heapq
import math
import random
from collections import Counter, deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Any

from simile.creatures import grid as moving
from simile.creatures.kinds import BOT
from simile.creatures.ways import Collect
from simile.schema import (
    Bionic,
    CreatureKind,
    Door,
    DoorKind,
    InteractableKind,
    Item,
    ItemKind,
    MapTile,
    Tile,
    TileArea,
)
from simile.street import charge
from simile.street.charge import Ways, runs, seconds
from simile.street.finds import searchable, under
from simile.street.jump import JUMP, KITS, LEGS, OWN_JUMP, Jump, meets
from simile.street.metro import BOT_SPAN, LIFT_FOOT, METRO, SALVAGE, SECRET, light, machine
from simile.street.moves import moves
from simile.street.plan import Pickup, Plan, Spawn
from simile.street.village import GROUND, plug, street
from simile.world.map import TownMap

SEWERS = "sewers"
LEVELS = 8
"""How many levels `simile street` writes to content/street/levels/."""
LANDING = MapTile(map=SEWERS, x=2, y=GROUND)
"""Where the lift from the metro stops."""
SHAFT = 12
"""The lift's landing is the first 12 cells, S8's, so a position saved there still stands."""
APEX_ACTUATOR = Item(id="apex_actuator", kind=ItemKind.PART, name="Apex actuator", weight=2.0)
"""The part the bionic legs' top grade needs, from Apex's own stock, on a pipe past every level's
gate."""
HATCH = "sewers_hatch"
"""The maintenance hatch deep in every level, a jack holding Aris's trail."""
GATE_BOX = "sewers_plug_1"
"""The junction box in the last column before the gate, at the end of the way in."""
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
RATS = (3, 2)
"""Zone 0's nests of rats, each keeping to a room of its own."""
BOT_FLOOR = 10
"""Cells of floor a bot has to itself at least, room to jump it as it comes."""
BOT_CLEAR = 2
"""Cells every cell of a bot's patrol keeps from where the player comes onto its floor."""
BOT_GAP = 8
"""Steps from any salvage that every cell of a bot's patrol keeps: over half a minute's drift."""
REACH = next(way.within for way in BOT.ways if isinstance(way, Collect))
"""How far by its own grid a bot notices salvage: every cell of its patrol is within it of some."""
DEN = 18
"""The dogs' den's width: a column of its own east of the last room."""
DOGS = 3
DEN_LADDER = 3
"""Cells in from the den's door that a ladder climbs to its loft, out of the dogs' reach."""
DEN_CLEAR = 2
"""Cells past that ladder before the floor the dogs keep to."""
BATS = (2, 2)
"""Zone 0's roosts of bats, each in a dark room of its own, the first on the way to the gate."""
CAVE = 18
"""The bat cave's width: a column of its own east of the den, three tiers high."""
CAVE_BATS = 30
"""Bats roosting under the cave's ceilings."""

ROOMS, HALL, SHAFT_KIND, GATE_KIND = "rooms", "hall", "shaft", "gate"
DEN_KIND, CAVE_KIND = "den", "cave"
SPRING_SECRET = "sewers_secret_spring"
SPRINT_SECRET = "sewers_secret_sprint"
SPRINT_SALVAGE = "sewers_salvage_sprint"
ACTUATOR_SECRET = "sewers_secret_actuator"
PIPE_SECRET = "sewers_secret_pipe"
DEN_SECRET = "sewers_secret_den"
CAVE_SECRET = "sewers_secret_cave"
TIERS = {SHAFT_KIND: (0,), ROOMS: (0, 1, 2), HALL: (0, 2), DEN_KIND: (), CAVE_KIND: ()}

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
SCRAP = {item.id: item for item in SALVAGE_ITEMS}

SECURITY_TERMINAL = "sewers_security_terminal"
"""A jack in a security station deep past the gate, teaching the infrared eye."""


@dataclass(frozen=True)
class Find:
    """Something to search in a level: a delver's bedroll, crates or the security terminal."""

    id: str
    zone: int
    """0 before the gate, reached on the player's own legs, or 1 past it, on any legs or feet."""
    piece: str
    items: tuple[str, ...] = ()
    """What it holds, by `SALVAGE_ITEMS` id."""
    teaches: Bionic | None = None
    security: bool = False
    """In the security station: the room past the gate farthest from it but the hatch's."""


LABELS = {"bedroll": "Delver's bedroll", "crates": "Crates", "dead_terminal": "Security terminal"}
WIDTHS = {"bedroll": 2, "crates": 1, "dead_terminal": 1}
FINDS = (
    Find("sewers_bedroll_legs", 0, "bedroll", ("copper_coil",), Bionic.BIONIC_LEGS),
    Find("sewers_crates_legs", 0, "crates", ("pump_impeller",) * 2),
    Find("sewers_bedroll_feet", 1, "bedroll", ("float_valve",), Bionic.SPRING_FEET),
    Find("sewers_crates_feet", 1, "crates", ("brass_fitting",) * 2),
    Find(SECURITY_TERMINAL, 1, "dead_terminal", teaches=Bionic.INFRARED_EYE, security=True),
    Find("sewers_bedroll_cell", 1, "bedroll", ("copper_coil",) * 2, Bionic.POWER_CELL_2, True),
    Find("sewers_crates_cell", 1, "crates", ("old_battery",) * 4),
)
"""Each level's recipes and their parts: the legs' before the gate, the feet's past it, and in the
security station the eye's with the second power cell's, which the eye needs."""
ZONES = {find.id: find.zone for find in FINDS}


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
                found += [(i, t) for t in TIERS[column.kind] if (i, t) != (self.spring_pocket, 2)]
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


def stock(level: Level, plan: Plan, shelves: list[tuple[Node, int]], cells: Stocker) -> None:
    """The hatch, the gate's junction box, the secrets and the salvage."""
    rng, gate = level.rng, level.gate
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
    nodes = [rng.choice([n for n in west if n[0] == gate - 1])]
    if rng.random() < 0.5:
        nodes.append(rng.choice([n for n in east if n != room]))  # kept so no level moves
    spot, *_ = [cells.take(node) for node in nodes]
    if spot is None:
        raise ValueError(f"no room for a plug in sewers level {level.seed}")
    box(plan, GATE_BOX, *spot)
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
    finds(level, plan, cells, rooms, room)


def finds(
    level: Level, plan: Plan, cells: Stocker, rooms: tuple[list[Node], list[Node]], hatch: Node
) -> None:
    """`FINDS`, each in a room of its zone with room for it, and the security station's together
    in the deepest room past the gate but the hatch's that has room for them all."""
    rng = level.rng
    station = [find for find in FINDS if find.security]
    spots: dict[str, Cell] = {}
    for node in (n for n in reversed(by_distance(level, (level.gate + 1, 0))) if n != hatch):
        taken = set(cells.taken)
        placed = {find.id: cells.take(node, WIDTHS[find.piece]) for find in station}
        if None not in placed.values():
            spots |= {id: spot for id, spot in placed.items() if spot is not None}
            break
        cells.taken = taken
    for find in FINDS:
        width = WIDTHS[find.piece]
        nodes = [n for n in rooms[find.zone] if cells.free(n, width)]
        if not find.security and nodes and (spot := cells.take(rng.choice(nodes), width)):
            spots[find.id] = spot
    for find in FINDS:
        if find.id not in spots:
            raise ValueError(f"no room for {find.id} in sewers level {level.seed}")
        spot = spots[find.id]
        width = WIDTHS[find.piece]
        x, row = spot
        height = 2 if find.piece == "dead_terminal" else 1
        area = TileArea(x=x, y=row + 1 - height, width=width, height=height)
        plan.piece(find.piece, area.x, area.y, width, height)
        jack = find.piece == "dead_terminal"
        kind = InteractableKind.JACK if jack else InteractableKind.SEARCHABLE
        items = [SCRAP[item] for item in find.items]
        label = LABELS[find.piece]
        searchable(plan, find.id, label, area, under(area), items, find.teaches, kind)


def box(plan: Plan, plug_id: str, x: int, row: int) -> None:
    """A junction box to charge the lamp at, in a lit stretch three cells wide."""
    area = TileArea(x=x, y=row - 1, width=1, height=2)
    plug(plan, plug_id, "Junction box", area, Tile(x=x, y=row))
    plan.piece("breaker_box", x, row - 1, 1, 2)
    left, right = max(x - 1, 0), min(x + 2, plan.width)
    light(plan, plug_id, left, row - 3, right - left, 4, lit=True)


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
    salvage = Pickup(SPRINT_SALVAGE, SALVAGE, end - 1, row, item=APEX_BOARD, needs=sprint)
    plan.pickups.append(salvage)


def farthest(level: Level, start: Node) -> Node:
    """The room the most doors and ladders from `start`."""
    return by_distance(level, start)[-1]


def by_distance(level: Level, start: Node) -> list[Node]:
    """The rooms joined to `start`, nearest first by doors and ladders."""
    near: dict[Node, list[Node]] = {}
    for edge in level.edges:
        a, b = level.ends(edge)
        near.setdefault(a, []).append(b)
        near.setdefault(b, []).append(a)
    seen, queue, order = {start}, deque([start]), []
    while queue:
        order.append(here := queue.popleft())
        for there in near.get(here, []):
            if there not in seen:
                seen.add(there)
                queue.append(there)
    return order


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


def dangers(level: Level, plan: Plan) -> None:
    """Zone 0's rats and bots, each where it has a solution: content/street/README.md's
    *Creatures*. A bot keeps to a floor of its own, long enough to jump it as it comes, and patrols
    clear of the ladders and holes onto it, to wait at out of its sight. A nest keeps to a room off
    every bot's floor, on its widest stretch, to come down on each rat as it comes."""
    rng = random.Random(f"sewers/{level.seed}/creatures")
    start, gate = level.columns[1].x, level.columns[level.gate].x
    zone = TileArea(x=start, y=0, width=gate - start, height=plan.height)

    def node(x: int, row: int) -> Node:
        c = next(i for i, column in enumerate(level.columns) if column.x <= x < column.end)
        return c, FLOORS.index(row)

    def floor(node: Node) -> list[int]:
        column = level.columns[node[0]]
        return [x for x in range(column.x, column.end) if plan.standing(x, FLOORS[node[1]])]

    salvage = [
        p for p in plan.pickups if p.kind == SALVAGE and p.needs is None and start <= p.x < gate
    ]
    grid = moving.Grid(Cells(plan), BOT, zone)  # type: ignore[arg-type]
    cells = [(x, y) for x in range(start, gate) for y in range(plan.height)]
    edges = {cell: list(grid.edges(cell)) for cell in cells if grid.allowed(cell)}
    costs = [towards(edges, (p.x, p.y), lambda edge: edge.cost) for p in salvage]
    steps = [towards(edges, (p.x, p.y), lambda edge: 1.0) for p in salvage]

    def patrol(cell: Cell) -> list[Cell]:
        return [cell, *grid.run(cell, -1, BOT_SPAN), *grid.run(cell, 1, BOT_SPAN)]

    def clear(cell: Cell) -> bool:
        return all(d.get(c, math.inf) >= BOT_GAP for c in patrol(cell) for d in steps)

    floors = stretches(edges)
    rooms = [n for n in level.nodes(0) if n[0] > 0 and level.columns[n[0]].kind == ROOMS]
    sizes = Counter(floors[c] for c in edges if plan.standing(*c))
    reached = {floors[c] for c in routes(Cells(plan), (LANDING.x, LANDING.y), JUMP) if c in floors}
    ways_on = [c for c in edges if plan.standing(*c) and onto(plan, *c, start, gate)]

    def unguarded(guarded: set[int]) -> list[Node]:
        return [n for n in rooms if not {floors.get((x, FLOORS[n[1]])) for x in floor(n)} & guarded]

    def passable(cell: Cell, apart: int = BOT_CLEAR) -> bool:
        """On a floor the player gets to on their own legs, long enough to jump the bot, its
        patrol `apart` from every way onto it."""
        here = floors[cell]
        ways = [w for w in ways_on if floors[w] == here]
        far = all(abs(w[0] - c[0]) >= apart for w in ways for c in patrol(cell))
        return here in reached and sizes[here] >= BOT_FLOOR and far

    used: list[Cell] = []
    for number in range(len(salvage)):
        taken = {floors[c] for c in used}
        own = [c for c in edges if plan.standing(*c) and floors[c] not in taken and clear(c)]
        free = sorted(c for c in own if passable(c)) or sorted(c for c in own if passable(c, 0))
        free = [c for c in free if len(unguarded(taken | {floors[c]})) >= len(RATS)]
        if not free:
            continue
        options = free
        for cost in sorted(costs, key=lambda cost: cost is not costs[number]):
            near = [c for c in free if all(cost.get(p, math.inf) <= REACH for p in patrol(c))]
            if near:
                options = near
                break
        x, y = rng.choice(options)
        used.append((x, y))
        bot = Spawn(f"sewers_bot_{len(used)}", CreatureKind.BOT, x, y, zone, BOT_SPAN)
        plan.creatures.append(bot)
    clear_of = unguarded({floors[c] for c in used})
    lying = {node(p.x, p.y) for p in salvage}
    choices = [[n for n in clear_of if n not in lying], clear_of, rooms]
    nests = rng.sample(next(c for c in choices if len(c) >= len(RATS)), len(RATS))
    number = 0
    for (c, tier), rats in zip(nests, RATS, strict=True):
        column, row = level.columns[c], FLOORS[tier]
        area = TileArea(x=column.x, y=row - 3, width=column.width, height=4)
        for x in sorted(rng.sample(widest(floor((c, tier))), rats)):
            number += 1
            plan.creatures.append(Spawn(f"sewers_rat_{number}", CreatureKind.RAT, x, row, area))


def widest(xs: list[int]) -> list[int]:
    """The longest run of neighbouring cells in `xs`, the first of them if two tie."""
    runs: list[list[int]] = []
    for x in xs:
        if runs and runs[-1][-1] == x - 1:
            runs[-1].append(x)
        else:
            runs.append([x])
    return max(runs, key=len)


def onto(plan: Plan, x: int, y: int, start: int, end: int) -> bool:
    """Whether the player comes onto a floor at (x, y) from elsewhere: at a ladder's foot or
    beside its top, at the edge of a hole they hop, under one they drop through, or at the zone's
    ends."""
    if x in (start, end - 1) or plan.climbable.get((x, y - 1)) is DoorKind.LADDER:
        return True
    for side in (x - 1, x + 1):
        if plan.climbable.get((side, y)) is DoorKind.LADDER is plan.climbable.get((side, y + 1)):
            return True
        if not plan.walkable(side, y) and (side, y) not in plan.solid:
            return True
    for up in range(y - 1, 0, -1):
        if (x, up) in plan.solid:
            return False
        if plan.standing(x - 1, up) or plan.standing(x + 1, up):
            return True
    return False


def stretches(edges: dict[Cell, list[moving.Edge]]) -> dict[Cell, int]:
    """Each cell's stretch of floor: the cells joined to it by `edges`, numbered."""
    found: dict[Cell, int] = {}
    for start in sorted(edges):
        if start in found:
            continue
        number, queue = len(set(found.values())), deque([start])
        found[start] = number
        while queue:
            for edge in edges[queue.popleft()]:
                if edge.to not in found:
                    found[edge.to] = number
                    queue.append(edge.to)
    return found


def den(level: Level, plan: Plan) -> None:
    """The dogs' den past the last room, and its loft: content/street/README.md's *The den*. The
    way past the dogs is up the ladder by the door, which they keep clear of, and along the loft."""
    rng = random.Random(f"sewers/{level.seed}/den")
    last, wall = len(level.columns) - 1, level.width
    column = Column(DEN_KIND, wall + 1, DEN, 1)
    level.columns.append(column)
    level.doors.add((last, 0))
    plan.width = level.width
    x, floor, loft = column.x, FLOORS[0], FLOORS[1]
    plan.fill(wall, 0, DEN + 1, CEILING + 1)
    plan.fill(wall, GROUND + 1, DEN + 1, plan.height - GROUND - 1)
    plan.fill(wall, CEILING + 1, 1, slab(1) - CEILING)
    ladder = column.end - 2
    plan.fill(x, slab(1), ladder - x, 1)
    plan.ladder((ladder, floor), floor - loft)
    plan.clear(x + DEN_LADDER - 1, slab(1), 2, 1)
    plan.ladder((x + DEN_LADDER, floor), floor - loft)
    light(plan, "sewers_den", wall, 0, DEN + 1, plan.height, lit=False)
    row = loft - 2
    plan.fill(x, row + 1, 2, 1)
    plan.piece("sewer_pipe", x, row + 1, 2, 1)
    money = float(rng.choice((90, 100, 110, 120)))
    plan.pickups.append(Pickup(DEN_SECRET, SECRET, x, row, money, needs=OWN_JUMP))
    plan.piece("bedroll", ladder - 3, loft, 2, 1)
    kept = x + DEN_LADDER + DEN_CLEAR
    area = TileArea(x=kept, y=floor - 3, width=column.end - kept, height=4)
    for number, at in enumerate(sorted(rng.sample(range(kept + 1, ladder), DOGS)), 1):
        plan.creatures.append(Spawn(f"sewers_dog_{number}", CreatureKind.DOG, at, floor, area))


def bats(level: Level, plan: Plan) -> None:
    """Zone 0's bats: content/street/README.md's *Creatures*. The way past them is in the dark."""
    rng = random.Random(f"sewers/{level.seed}/bats")
    rooms = [n for n in level.nodes(0) if n[0] > 0 and level.columns[n[0]].kind == ROOMS]
    dark = [n for n in rooms if roosts(level, plan, n) and not lit(plan, level, n)]
    way = [n for n in between(level, (0, 0), (level.gate - 1, 0)) if n in dark]
    first = rng.choice(way or dark)
    others = [n for n in dark if n != first]
    if not others:
        raise ValueError(f"no dark rooms for zone 0's bats in sewers level {level.seed}")
    nodes = [first, rng.choice(others)]
    number = 0
    for (c, tier), count in zip(nodes, BATS, strict=True):
        column, row = level.columns[c], FLOORS[tier]
        area = TileArea(x=column.x, y=row - 3, width=column.width, height=4)
        for x in sorted(rng.sample(roosts(level, plan, (c, tier)), count)):
            number += 1
            bat = Spawn(f"sewers_bat_{number}", CreatureKind.BAT, x, row - 3, area)
            plan.creatures.append(bat)


def roosts(level: Level, plan: Plan, node: Node) -> list[int]:
    """Where a bat hangs in a room: under its ceiling, not over a hole."""
    column, top = level.columns[node[0]], FLOORS[node[1]] - 3
    return [x for x in range(column.x, column.end) if (x, top - 1) in plan.solid]


def lit(plan: Plan, level: Level, node: Node) -> bool:
    """Whether a lit stretch reaches into the room."""
    column, row = level.columns[node[0]], FLOORS[node[1]]
    room = TileArea(x=column.x, y=row - 3, width=column.width, height=4)
    return any(
        light.lit
        and light.area.x < room.x + room.width
        and room.x < light.area.x + light.area.width
        and light.area.y < room.y + room.height
        and room.y < light.area.y + light.area.height
        for light in plan.light
    )


def between(level: Level, start: Node, end: Node) -> list[Node]:
    """The rooms on the way from `start` to `end` by doors and ladders."""
    near: dict[Node, list[Node]] = {}
    for edge in level.edges:
        a, b = level.ends(edge)
        near.setdefault(a, []).append(b)
        near.setdefault(b, []).append(a)
    came: dict[Node, Node | None] = {start: None}
    queue = deque([start])
    while queue:
        for there in near.get(here := queue.popleft(), []):
            if there not in came:
                came[there] = here
                queue.append(there)
    way: list[Node] = []
    at: Node | None = end if end in came else None
    while at is not None:
        way.append(at)
        at = came[at]
    return way[::-1]


def cave(level: Level, plan: Plan) -> None:
    """The bat cave past the den: content/street/README.md's *The cave*. The way past its bats is
    in the dark, and in from the den's loft past the dogs."""
    rng = random.Random(f"sewers/{level.seed}/cave")
    den, wall = len(level.columns) - 1, level.width
    column = Column(CAVE_KIND, wall + 1, CAVE, 1)
    level.columns.append(column)
    level.doors.add((den, 0))
    plan.width = level.width
    x, end = column.x, column.end
    plan.fill(wall, 0, CAVE + 1, CEILING + 1)
    plan.fill(wall, GROUND + 1, CAVE + 1, plan.height - GROUND - 1)
    plan.fill(wall, CEILING + 1, 1, FLOORS[1] - 3 - CEILING - 1)
    plan.fill(wall, slab(1), 1, 1)
    level.doors.add((den, 1))
    ledge = end - 2
    up = ledge - GAP - 2
    plan.fill(x, slab(1), up - x, 1)
    plan.ladder((up, FLOORS[0]), FLOORS[0] - FLOORS[1])
    plan.fill(x + 2, slab(2), ledge - GAP - x - 2, 1)
    plan.fill(ledge, slab(2), 2, 1)
    plan.ladder((x + 1, FLOORS[1]), FLOORS[1] - FLOORS[2])
    light(plan, "sewers_cave", wall, 0, CAVE + 1, plan.height, lit=False)
    money = float(rng.choice((140, 160, 180, 200)))
    stash = Pickup(CAVE_SECRET, SECRET, end - 1, FLOORS[2], money, needs=Bionic.BIONIC_LEGS)
    plan.pickups.append(stash)
    area = TileArea(x=x, y=CEILING + 1, width=CAVE, height=GROUND - CEILING)
    hanging = [(FLOORS[t] - 3, at) for t in range(3) for at in roosts(level, plan, (den + 1, t))]
    for number, (top, at) in enumerate(sorted(rng.sample(hanging, CAVE_BATS)), 1):
        bat = Spawn(f"sewers_cave_bat_{number}", CreatureKind.BAT, at, top, area)
        plan.creatures.append(bat)


def stops(town: Any, zone: int) -> list[Cell]:
    [gate] = [light.area for light in town.light if light.id == "sewers_gate"]
    things = [
        (item.stand[0].x, item.stand[0].y)
        for item in town.interactables
        if item.id in ZONES or item.id == HATCH
    ]
    things += [
        (pickup.x, pickup.y)
        for pickup in town.pickups
        if pickup.id.removeprefix("sewers_salvage_").isdigit()
        or pickup.id in (PIPE_SECRET, ACTUATOR_SECRET, DEN_SECRET)
    ]
    if zone == 0:
        return [cell for cell in things if cell[0] < gate.x]
    legs = [(p.x, p.y) for p in town.pickups if p.id in (SPRINT_SECRET, SPRINT_SALVAGE)]
    return [*(cell for cell in things if cell[0] >= gate.x + gate.width), *legs]


def gate_box(town: Any) -> Cell:
    [stand] = [item.stand[0] for item in town.interactables if item.id == GATE_BOX]
    return stand.x, stand.y


def way_in(town: Any) -> list[Cell]:
    return Ways(town).tour((LANDING.x, LANDING.y), stops(town, 0), gate_box(town))


def way_on(town: Any) -> list[Cell]:
    start = gate_box(town)
    return Ways(town, LEGS[Bionic.BIONIC_LEGS]).tour(start, stops(town, 1), start)


def boxes(level: Level, plan: Plan, cells: Stocker) -> None:
    town, route = Cells(plan), way_on(Cells(plan))
    floors = {(x, FLOORS[node[1]]) for node in level.nodes(1) for x in cells.free(node)}
    plugs = {
        (item.stand[0].x, item.stand[0].y)
        for item in plan.interactables
        if item.kind is InteractableKind.PLUG
    }

    def runs_out(plugs: set[Cell]) -> int:
        """How far along the way the lamp runs past its reach, or its end if it never does."""
        spent = 0.0
        for i, (a, b) in enumerate(pairwise(route)):
            if not (town.lit(*a) and town.lit(*b)):
                spent += seconds(town, a, b)
            if spent > charge.REACH:
                return i
            if b in plugs:
                spent = 0.0
        return len(route)

    while runs_out(plugs) < len(route):
        spots = [c for c in dict.fromkeys(route) if c in floors and c not in cells.taken]
        if not spots:
            raise ValueError(f"no room for a junction box in sewers level {level.seed}")

        def first(c: Cell) -> tuple[int, float]:
            return runs_out(plugs | {c}), runs(town, route, plugs | {c})[0]

        x, row = max(spots, key=first)
        cells.taken |= {(x + d, row) for d in (-1, 0, 1)}
        box(plan, f"sewers_plug_{len(plugs) + 1}", x, row)
        plugs.add((x, row))


def towards(
    edges: dict[Cell, list[moving.Edge]], goal: Cell, cost: Callable[[moving.Edge], float]
) -> dict[Cell, float]:
    """The least `cost` from each cell to `goal` by `edges`."""
    into: dict[Cell, list[tuple[Cell, moving.Edge]]] = {}
    for cell, ways in edges.items():
        for edge in ways:
            into.setdefault(edge.to, []).append((cell, edge))
    found: dict[Cell, float] = {}
    frontier = [(0.0, goal)]
    while frontier:
        spent, here = heapq.heappop(frontier)
        if here in found:
            continue
        found[here] = spent
        for there, edge in into.get(here, []):
            if there not in found:
                heapq.heappush(frontier, (spent + cost(edge), there))
    return found


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
    cells = Stocker(level, plan)
    stock(level, plan, ledges, cells)
    dangers(level, plan)
    bats(level, plan)
    den(level, plan)
    cave(level, plan)
    boxes(level, plan, cells)
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
        self.id, self.doors = plan.id, plan.doors
        self.interactables, self.pickups, self.light = plan.interactables, plan.pickups, plan.light

    def solid(self, x: int, y: int) -> bool:
        return not (0 <= x < self.width and 0 <= y < self.height) or (x, y) in self.plan.solid

    def climb(self, x: int, y: int) -> DoorKind | None:
        return self.plan.climbable.get((x, y))

    def walkable(self, x: int, y: int) -> bool:
        return self.plan.walkable(x, y)

    def standing(self, x: int, y: int) -> bool:
        return self.plan.standing(x, y)

    def lit(self, x: int, y: int) -> bool:
        return TownMap.lit(self, x, y)  # type: ignore[arg-type]


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
    held = {item.id: item for item in plan.interactables if item.id in ZONES}
    if missing := sorted(set(ZONES) - set(held)):
        found.append(f"no {', '.join(missing)}")
    near = [held[id] for id, zone in ZONES.items() if zone == 0 and id in held]
    deep = [held[id] for id, zone in ZONES.items() if zone == 1 and id in held]
    for item in [hatch, *plugs, *near, *deep]:
        cell = (item.stand[0].x, item.stand[0].y)
        missed = [name for name in KITS if name != OWN_JUMP and cell not in reached[name]]
        if item in near and cell not in reached[OWN_JUMP]:
            missed.insert(0, OWN_JUMP)
        if missed:
            found.append(f"{item.id} is out of reach of {', '.join(missed)}")
    for item in [hatch, *deep]:
        if (item.stand[0].x, item.stand[0].y) in reached[OWN_JUMP]:
            found.append(f"{item.id} is in reach of the player's own legs")
    for pickup in plan.pickups:
        cell = (pickup.x, pickup.y)
        for name, jump in KITS.items():
            reaches = cell in reached[name]
            if name != OWN_JUMP and reaches != meets(jump, pickup.needs or OWN_JUMP):
                found.append(f"{pickup.id} needs {pickup.needs}, but {name} says otherwise")
        if pickup.needs not in (None, OWN_JUMP) and cell in reached[OWN_JUMP]:
            found.append(f"{pickup.id} is in reach of the player's own legs")
    return found
