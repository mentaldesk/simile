"""Every danger has a solution: a scripted player past every creature on the metro and every
level of the sewers, losing no health (simile/creatures/README.md's *Solutions*)."""

import heapq
import math
from collections.abc import Iterable, Iterator
from functools import cache

import pytest

from simile.creatures.engine import Creature
from simile.creatures.kinds import BOT, RAT
from simile.creatures.placing import spawns
from simile.schema import Bionic, Body, CreatureKind, CreatureState, Item, ItemKind, Player
from simile.street.jump import JUMP, LEGS, Jump
from simile.street.metro import VAULT_LADDER
from simile.street.moves import moves
from simile.street.plan import Spawn
from simile.street.sewers import DEN, DEN_LADDER, FLOORS, LANDING, LEVELS, SEWERS, WEIR_AT
from simile.world.map import TownMap, load_maps

from .walkthrough import FRAME, Climb, Leap, Plan, Step, Stuck, Wait, Walk, Walkthrough

type Cell = tuple[int, int]

FRAMES = (0.02, FRAME, 0.1)
"""Seconds of the client's a step of the player's moves takes: each run passes at any of them."""
FITTED = Body(vertebra=Bionic.DATAJACK)
"""As the player comes back from the clinic, so the bots go for them."""
LEGGED = Body(vertebra=Bionic.DATAJACK, legs=Bionic.BIONIC_LEGS)
FOOD = Item(id="ration_bar", kind=ItemKind.FOOD, name="Ration bar", weight=0.2)
"""So the rats go for them too."""
JUMPING = 3.0
"""What a jump adds to a way's cost, on top of twice its length, so the player walks and climbs
where they can, and jumps no further than they have to."""
JUMP_OVER = 2.0
"""Tiles from a bot coming at them that the player jumps it."""
CLEARS = 3.4
"""Tiles along that jump lands, well past it."""
STOMPS = 1.5
"""Tiles from a rat that the player hops, to come down on it."""
COMING = {CreatureState.CHASING, CreatureState.ATTACKING}
LEAD = 2.5
"""Tiles a bot coming for the player is behind them at least as they start to climb, or else
they lead it away first."""
LURE = 6.0
"""Tiles from a ladder's foot the player leads a bot."""
DODGES = 12
"""How many times the player dodges on the way to one place before it's no way at all."""
PER_DANGER = 40.0
"""Seconds the player takes at most to get past each danger, waiting for it or leading it away."""
LADDER_CLEAR = {BOT: 3.0, RAT: 1.5}
"""Tiles a bot or a rat keeps from a ladder's end before the player goes on up or down it."""


@cache
def maps(level: int = 0) -> dict[str, TownMap]:
    return load_maps(level=level)


def placed(map_id: str, level: int = 0) -> list[tuple[str, Spawn]]:
    return [(m, spawn) for m, spawn in spawns(level=level) if m == map_id]


# The metro


EAST = [
    Walk(32),
    Climb(12),
    Walk(42.6),
    Leap(45, 10),
    Walk(VAULT_LADDER),
    Climb(15),
    Walk(70),
]
"""From the foot of the stairs to the plug, over both bots: `BOTS` in `simile.street.metro`."""
WEST = [
    Walk(VAULT_LADDER),
    Climb(10),
    Walk(44.6),
    Leap(42, 12),
    Walk(32),
    Climb(15),
    Walk(23),
]


def metro(steps: Iterable[Step], body: Body = FITTED, frame: float = FRAME) -> Walkthrough:
    town = maps()["metro"]
    walk = Walkthrough(town, placed("metro"), 23, 15, player=Player(body=body), frame=frame)
    return walk.go(steps)


@pytest.mark.parametrize("frame", FRAMES)
def test_the_metro_s_bots_are_passed_overhead_both_ways_unhurt(frame: float) -> None:
    walk = metro([*EAST, Walk(70.5), *WEST], frame=frame)
    assert walk.harmed == [], walk.log


def test_walking_the_metro_s_floor_hurts_a_fitted_player_but_not_a_whole_one() -> None:
    for frame in FRAMES:
        assert metro([Walk(70), Walk(23)], frame=frame).harmed, frame
    assert metro([Walk(70), Walk(23)], Body()).harmed == []


# The sewers


def way(town: TownMap, start: Cell, goals: set[Cell], jump: Jump) -> list[Cell]:
    """The cheapest cells to the nearest of `goals`, walking and climbing where they can."""
    frontier, came = [(0.0, start)], {start: start}
    spent = {start: 0.0}
    while frontier:
        cost, cell = heapq.heappop(frontier)
        if cell in goals:
            cells = [cell]
            while cell != start:
                cell = came[cell]
                cells.append(cell)
            return cells[::-1]
        if cost > spent[cell]:
            continue
        for move in moves(town, cell, jump):
            if town.solid(move.cell[0], move.cell[1] - 1):
                continue
            dx, dy = move.cell[0] - cell[0], move.cell[1] - cell[1]
            jumps = abs(dx) + abs(dy) != 1
            total = cost + move.cost * (1 + jumps) + JUMPING * jumps
            if total < spent.get(move.cell, math.inf):
                spent[move.cell], came[move.cell] = total, cell
                heapq.heappush(frontier, (total, move.cell))
    raise Stuck(f"no way from {start} to {sorted(goals)[:3]}")


def steps(town: TownMap, cells: list[Cell]) -> list[Step]:
    """Walks along floors, climbs and leaps, for the cells of a way."""
    found: list[Step] = []
    for (x, y), (nx, ny) in zip(cells, cells[1:], strict=False):
        last = found[-1] if found else None
        if ny == y and abs(nx - x) == 1:
            if isinstance(last, Walk):
                found.pop()
            found.append(Walk(nx))
        elif nx == x and abs(ny - y) == 1:
            if isinstance(last, Climb):
                found.pop()
            found.append(Climb(ny))
        else:
            side = 1 if nx > x else -1
            edge = not town.standing(x + side, y) and not town.solid(x + side, y)
            if nx != x and edge and town.standing(x, y):
                found.append(Walk(x + 0.45 * side))
            found.append(Leap(nx, ny, rise=0.0 if ny > y and abs(nx - x) <= 1 else None))
    return found


def to(goals: set[Cell] | Cell) -> Plan:
    """The way from wherever they are to the nearest of `goals`, again whenever they've had to
    dodge something on it."""
    ends = goals if isinstance(goals, set) else {goals}

    def plan(walk: Walkthrough) -> Iterator[Step | Plan]:
        start = walk.reactions
        while True:
            here, seen = (round(walk.x), round(walk.y)), walk.reactions
            if seen - start > DODGES:
                raise Stuck(f"still dodging on the way to {sorted(ends)[:3]}")
            for step in steps(walk.town, way(walk.town, here, ends, walk.jump)):
                if isinstance(step, Climb) and (bot := guarding(walk)) is not None:
                    yield lure(walk, bot, walk.x)
                    break
                yield step
                if walk.reactions != seen:
                    break
            else:
                return

    return plan


def guarding(walk: Walkthrough) -> Creature | None:
    """A bot coming for them along the floor they're about to climb from."""
    row = round(walk.y)
    if not walk.town.standing(round(walk.x), row):
        return None
    return next(
        (
            bot
            for bot in alive(walk, BOT)
            if math.isclose(bot.y, row) and bot.state in COMING and abs(bot.x - walk.x) < LEAD
        ),
        None,
    )


def lure(walk: Walkthrough, bot: Creature, foot: float) -> Plan:
    """Leads a bot away from `foot`, where the player stops to climb: runs off along the floor,
    away from it if there's room, waits for it to come, jumps it and runs back with a lead on it."""
    row = round(walk.y)
    cells = sorted(x for x, y in _stretch(bot) if y == row)
    side = -1 if bot.x > foot else 1
    away = [x for x in cells if (x - foot) * side >= LURE]
    there = away or [x for x in cells if abs(x - foot) >= LURE]
    far = min(there, key=lambda x: abs(x - foot))
    back = 1 if foot > far else -1

    def coming(walk: Walkthrough) -> bool:
        return bot.state in COMING and 0 < (bot.x - walk.x) * back <= JUMP_OVER

    def plan(walk: Walkthrough) -> Iterator[Step | Plan]:
        while not math.isclose(walk.x, far):
            yield Walk(far, walk.jump.run)
        yield Wait(6, until=coming)
        if coming(walk):
            yield Leap(walk.x + back * CLEARS, row)
        while not math.isclose(walk.x, foot):
            yield Walk(foot, walk.jump.run)

    return plan


def alive(walk: Walkthrough, kind: object) -> Iterable[Creature]:
    return (c for c in walk.creatures.all.values() if c.kind is kind and c.down is None)


def dodge(walk: Walkthrough, step: Step) -> list[Step | Plan] | None:
    """Waits on a ladder, or before jumping onto a floor, for a bot by where they'll come onto it
    to go; comes down on a rat that's coming for them, and jumps a bot that is."""
    if isinstance(step, Climb):
        return _wait_on_ladder(walk, step)
    if isinstance(step, Leap):
        return _wait_to_leap(walk, step)
    row = round(walk.y)
    if not math.isclose(walk.y, row) or not walk.town.standing(round(walk.x), row):
        return None
    rats = [c for c in alive(walk, RAT) if math.isclose(c.y, row) and c.state in COMING]
    if any(abs(rat.x - walk.x) <= STOMPS for rat in rats):
        return [Leap(walk.x, row)]
    way = 0 if isinstance(step, Wait) else (1 if step.x > walk.x else -1)
    for bot in alive(walk, BOT):
        ahead = (bot.x - walk.x) * way
        if not (math.isclose(bot.y, row) and bot.state in COMING and ahead > 0):
            continue
        if isinstance(step, Walk) and abs(step.x - walk.x) < abs(bot.x - walk.x):
            if abs(bot.x - step.x) < LEAD and ahead <= LEAD + 1:
                return [lure(walk, bot, step.x)]
            continue
        if ahead <= JUMP_OVER:
            land = walk.x + way * CLEARS
            cells = range(round(walk.x), round(land) + way, way)
            if walk.town.standing(round(land), row) and all(
                walk.town.walkable(x, row) for x in cells
            ):
                return [Leap(land, row)]
    return None


def _wait_to_leap(walk: Walkthrough, step: Leap) -> list[Step] | None:
    """Out of sight on another floor till no bot is by where they'll land on its."""
    here, there = sorted((round(walk.x), round(step.x)))
    if math.isclose(step.row, walk.y) and all(
        walk.town.walkable(x, step.row) for x in range(here, there + 1)
    ):
        return None

    def near(walk: Walkthrough) -> bool:
        return any(
            math.isclose(bot.y, step.row) and abs(bot.x - step.x) <= LADDER_CLEAR[BOT]
            for bot in alive(walk, BOT)
        )

    return [Wait(until=lambda walk: not near(walk))] if near(walk) else None


def _wait_on_ladder(walk: Walkthrough, step: Climb) -> list[Step] | None:
    """Out of sight on the ladder a row short of its end, till no bot or rat is near it."""
    if not 1.0 < abs(step.row - walk.y) <= 1.3:
        return None

    def near(walk: Walkthrough) -> bool:
        return any(
            math.isclose(c.y, step.row) and abs(c.x - walk.x) <= clear
            for kind, clear in LADDER_CLEAR.items()
            for c in alive(walk, kind)
        )

    return [Wait(until=lambda walk: not near(walk))] if near(walk) else None


def floor(town: TownMap, row: int, xs: range) -> set[Cell]:
    return {(x, row) for x in xs if town.standing(x, row)}


def past(town: TownMap, spawn: Spawn) -> Plan:
    """Across the floor a bot keeps to, from wherever they come onto it to past where it starts."""

    def plan(walk: Walkthrough) -> list[Step | Plan]:
        bot = walk.creature(spawn.id)
        stretch = _stretch(bot)
        here = (round(walk.x), round(walk.y))
        onto = next(c for c in way(walk.town, here, stretch, walk.jump) if c in stretch)
        side = 1 if bot.home[0] >= onto[0] else -1
        beyond = [c for c in stretch if (c[0] - bot.home[0]) * side >= 0]
        far = min(beyond, key=lambda c: abs(c[0] - (bot.home[0] + 4 * side)))
        return [to(far)]

    return plan


def _stretch(bot: Creature) -> set[Cell]:
    found, queue = {bot.home}, [bot.home]
    while queue:
        for edge in bot.grid.edges(queue.pop()):
            if edge.to not in found:
                found.add(edge.to)
                queue.append(edge.to)
    return {c for c in found if bot.grid.town.standing(*c)}


def across(town: TownMap, spawn: Spawn) -> Plan:
    """From one end to the other of the room a roost keeps to."""
    area = spawn.area
    assert area is not None
    room = floor(town, area.y + area.height - 1, range(area.x, area.x + area.width))

    def plan(walk: Walkthrough) -> list[Step | Plan]:
        here = (round(walk.x), round(walk.y))
        near = way(walk.town, here, room, walk.jump)[-1]
        far = max(way_within(walk.town, near, room), key=lambda c: abs(c[0] - near[0]))
        return [to(near), to(far)]

    return plan


def stomping(town: TownMap, spawn: Spawn) -> Plan:
    """Into each stretch of the room a nest keeps to, to stand in its middle while they come at
    the food, and come down on each of them."""
    area = spawn.area
    assert area is not None
    room = floor(town, area.y + area.height - 1, range(area.x, area.x + area.width))

    def plan(walk: Walkthrough) -> Iterator[Step | Plan]:
        rats = [c for c in walk.creatures.all.values() if c.kind is RAT and c.grid.area == area]
        parts = {tuple(way_within(walk.town, rat.home, room)) for rat in rats}
        for part in sorted(parts):
            homes = set(part)

            def gone(walk: Walkthrough, homes: set[Cell] = homes) -> bool:
                return all(rat.down is not None for rat in rats if rat.home in homes)

            clear = [
                c for c in part if not walk.town.climb(*above(c)) and not walk.town.solid(*above(c))
            ]
            yield to(clear[len(clear) // 2])
            yield Wait(until=gone, timeout=30)

    return plan


def above(cell: Cell) -> Cell:
    return cell[0], cell[1] - 1


def way_within(town: TownMap, start: Cell, cells: set[Cell]) -> list[Cell]:
    found, queue = {start}, [start]
    while queue:
        x, y = queue.pop()
        for nx in (x - 1, x + 1):
            if (nx, y) in cells and (nx, y) not in found:
                found.add((nx, y))
                queue.append((nx, y))
    return sorted(found)


def dangers(level: int) -> list[tuple[CreatureKind, Spawn]]:
    """Zone 0's creatures, one of each nest and roost, in the order they're placed."""
    seen, found = set(), []
    for _, spawn in placed(SEWERS, level):
        if "cave" in spawn.id or spawn.kind is CreatureKind.DOG:
            continue
        area = spawn.area
        key = (
            spawn.id
            if spawn.kind is CreatureKind.BOT or area is None
            else (spawn.kind, area.x, area.y)
        )
        if key not in seen:
            seen.add(key)
            found.append((spawn.kind, spawn))
    return found


def sewers(level: int, jump: Jump, body: Body, frame: float) -> Walkthrough:
    town, start = maps(level)[SEWERS], (LANDING.x, LANDING.y)
    player = Player(body=body, items=[FOOD])
    return Walkthrough(town, placed(SEWERS, level), *start, player, jump, react=dodge, frame=frame)


def nearest_first(walk: Walkthrough, plans: list[tuple[set[Cell], Plan]]) -> Iterator[Plan]:
    """Each plan in turn, the nearest first, each in at most `PER_DANGER` seconds."""
    left = list(plans)
    while left:
        here = (round(walk.x), round(walk.y))
        costs = [len(way(walk.town, here, cells, walk.jump)) for cells, _ in left]
        start = walk.now
        yield left.pop(costs.index(min(costs)))[1]
        yield lambda walk, start=start: _in_time(walk, start)


def _in_time(walk: Walkthrough, start: float) -> list[Step]:
    if walk.now - start > PER_DANGER:
        raise Stuck(f"{walk.now - start:.0f} s getting past one danger")
    return []


def where(walk: Walkthrough, spawn: Spawn) -> set[Cell]:
    """The floor a danger keeps to."""
    if spawn.kind is CreatureKind.BOT:
        return _stretch(walk.creature(spawn.id))
    area = spawn.area
    assert area is not None
    return floor(walk.town, area.y + area.height - 1, range(area.x, area.x + area.width))


def zone_0(level: int, frame: float = FRAME) -> Walkthrough:
    """From the lift past every rat, bot and bat before the gate, to the gate's weir, on the
    player's own legs."""
    walk = sewers(level, JUMP, FITTED, frame)
    town = walk.town
    ways = {CreatureKind.BOT: past, CreatureKind.RAT: stomping}
    plans = [
        (where(walk, spawn), ways.get(kind, across)(town, spawn)) for kind, spawn in dangers(level)
    ]
    walk.go(nearest_first(walk, plans))
    [gate] = [light.area.x for light in town.light if light.id == "sewers_gate"]
    return walk.go([to((gate + WEIR_AT - 1, FLOORS[0]))])


def den(level: int, frame: float = FRAME) -> Walkthrough:
    """From the lift on the first legs through the gate to the den, up its ladder by the door to
    the loft's stash, along the loft into the bat cave by lamplight off, and back out."""
    walk = sewers(level, LEGS[Bionic.BIONIC_LEGS], LEGGED, frame)
    town = walk.town
    [door] = [light.area.x for light in town.light if light.id == "sewers_den"]
    x, end, loft, ground = door + 1, door + 1 + DEN, FLOORS[1], FLOORS[0]
    ladder = x + DEN_LADDER
    walk.go([to((door - 1, ground))])
    walk.go(
        [
            Walk(ladder),
            Climb(loft),
            Walk(ladder + 1),
            Walk(ladder + 1.4),
            Leap(x, loft - 2),
            Leap(ladder + 1, loft),
            Walk(end - 3.4),
            Leap(end, loft),
            Walk(end + 3),
            Walk(end - 0.4),
            Leap(end - 3, loft),
            Walk(ladder),
            Climb(ground),
            Walk(door - 3),
        ]
    )
    return walk


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("level", range(LEVELS))
def test_every_danger_before_the_gate_is_passed_unhurt_on_the_player_s_own_legs(
    level: int, frame: float
) -> None:
    walk = zone_0(level, frame)
    assert walk.harmed == [], "\n".join(walk.log[-40:])


@pytest.mark.parametrize("frame", FRAMES)
@pytest.mark.parametrize("level", range(LEVELS))
def test_the_den_s_stash_and_the_cave_are_reached_past_the_dogs_unhurt(
    level: int, frame: float
) -> None:
    walk = den(level, frame)
    assert walk.harmed == [], "\n".join(walk.log[-40:])
