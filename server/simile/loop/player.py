import heapq
import json
import math
from collections import Counter, deque
from collections.abc import Collection, Iterator, Sequence
from datetime import datetime, timedelta
from itertools import pairwise

from pydantic import BaseModel
from starlette.applications import Starlette

from simile.behaviour import Activity
from simile.clinic.config import DEFAULT_CONFIG as CLINIC
from simile.combat.shooting import RANGE
from simile.creatures.grid import sees
from simile.economy.config import SALVAGE
from simile.machines.workshop import MACHINES
from simile.player.lamp import DEFAULT_LAMP
from simile.protocol import (
    ConversationEndedMessage,
    ConversationStartedMessage,
    Creature,
    CreatureGoneMessage,
    CreatureHitMessage,
    CreatureMovedMessage,
    EatMessage,
    FireMessage,
    FitMessage,
    JournalMessage,
    LampMessage,
    LineMessage,
    MachineChangedMessage,
    MakeMessage,
    PickUpMessage,
    PlayerDiedMessage,
    PlayerMoveMessage,
    PlayerSayMessage,
    PlayerStateMessage,
    Position,
    ReloadMessage,
    RepairMessage,
    SellMessage,
    SellPartMessage,
    SellRecipeMessage,
    StashMessage,
    TakeMessage,
    hub_of,
)
from simile.protocol.messages import server_messages
from simile.schema import (
    PLAYER_ID,
    SOLD,
    Bionic,
    BodyPart,
    Corpse,
    CreatureKind,
    CreatureState,
    DoorKind,
    Id,
    Interactable,
    InteractableKind,
    Item,
    ItemKind,
    JournalEntry,
    Machine,
    MachineState,
    MapTile,
    Pile,
    Player,
    SideFacing,
)
from simile.sim import world_of
from simile.street.charge import CLIMB, JUMPING
from simile.street.finds import COPPER_PIPE
from simile.street.jump import Jump, jump_of
from simile.street.moves import moves, possible
from simile.street.sewers import SEWERS
from simile.voicing.distance import between
from simile.world import Point, movement_of
from simile.world.map import WALKING_SPEED, Pickup, TownMap
from simile.world.paths import CROSSING_SPEED, DOOR, Spot, octile

HOME, BUYERS = "maker_space", ("clinic", "scrap_stall")
LOCKERS = "lockers"
HUNGRY = 0.5
NEAR = 2.0
"""How near a resident, in tiles along the street, the player walks up before talking."""
FOLLOW = 4
QUIET = 10
"""Sim seconds without a line before a reply is over: longer than a goodbye waits for an answer."""
SKIPPED = ('{"type":"entity_moved"', '{"type":"clock"', '{"type":"npc_state"')
SAMPLE = 0.1
"""Sim seconds between the positions the player sends as they move."""
GUARDED = 40.0
"""What a cell adds to a way's cost in sight of a bot or a dog on its floor."""
SIGHT = {CreatureKind.BOT: 7.0, CreatureKind.DOG: 14.0}
COMING = {CreatureState.CHASING, CreatureState.ATTACKING}
JUMP_OVER = 2.6
"""Tiles from a bot coming at them that they jump it."""
STOMPS = 1.6
"""Tiles from a rat coming for their food that they hop, to come down on it."""
CLEAR = {CreatureKind.BOT: 3.5, CreatureKind.RAT: 2.0, CreatureKind.DOG: 1.8}
"""Tiles a creature keeps from where they'd come onto its floor before they do."""
BATS = 10.0
"""Tiles from a bat in sight of which their lamp stays off: further than a bat sees."""
PLAN = 30
"""How many times they plan a way again after dodging something on it."""
WAITS = 40.0
"""Sim seconds they wait at most for a creature to move off."""
LIGHT = DEFAULT_LAMP.light
USED = {
    *(id for recipe in CLINIC.recipes.values() for id in recipe.parts),
    *(id for machine in MACHINES.values() for id in machine.parts),
    COPPER_PIPE.id,
}
SCRAP = frozenset(SALVAGE) - USED
"""What the recycler presses into plastic: the salvage no recipe or repair uses, but copper pipe."""


class Refused(Exception):
    """The server didn't do what the player's message asked."""


def amounts(items: Collection[Item]) -> Counter[str]:
    """How many of each item, by id."""
    counted: Counter[str] = Counter()
    for item in items:
        counted[item.id] += item.amount
    return counted


class LoopPlayer:
    """A client in the game that plays by the client's messages, and knows only what it's sent."""

    def __init__(self, app: Starlette, notes: list[str]) -> None:
        self.hub, self.world, self.movement = hub_of(app), world_of(app), movement_of(app)
        self.behaviour = app.state.behaviour
        self.notes = notes
        self.state = PlayerStateMessage(player=Player())
        self.journal: list[JournalEntry] = []
        self.creatures: dict[Id, Creature] = {}
        self.mine: set[str] = set()
        """The conversations with the player."""
        self.heard: deque[LineMessage] = deque(maxlen=200)
        self.ended: set[str] = set()
        self.where: Point | None = None
        self.away = timedelta()
        """Sim time skipped while out of the game."""
        self.hurt: list[str] = []
        """Each time they lost health, or died."""
        self.dark: list[str] = []
        """Each time their lamp ran flat in the dark."""
        self.stomped = 0
        self.leapt = 0
        self.roused: set[Id] = set()
        """The bats that came for them."""
        self.by_bats = False
        self.lamp_off_by_bats = 0
        self.machines: dict[Id, Machine] = {}
        self.hit: list[Id] = []
        """Each creature a shot of theirs hit, in order."""
        self.shot: Counter[CreatureKind] = Counter()
        """The creatures their shots put down, by kind."""
        self.died: list[str] = []
        self._reach: dict[Jump, set[Spot]] = {}

    @property
    def player(self) -> Player:
        return self.state.player

    @property
    def money(self) -> float:
        return self.player.money

    @property
    def at(self) -> Spot:
        assert self.where is not None
        here = self.where
        return Spot(here.map, math.floor(here.x + 0.5), math.ceil(round(here.y, 6)))

    def put(self, frame: str | bytes) -> None:
        if isinstance(frame, bytes) or frame.startswith(SKIPPED):
            return
        match server_messages.validate_python(json.loads(frame)):
            case PlayerStateMessage() as state:
                self._vitals(self.state.player, state.player)
                self.state = state
            case JournalMessage(entries=entries):
                self.journal = entries
            case CreatureMovedMessage(creature=creature):
                self.creatures[creature.id] = creature
                if creature.kind is CreatureKind.BAT and creature.state in COMING:
                    self.roused.add(creature.id)
            case CreatureGoneMessage(creature_id=id):
                self.creatures.pop(id, None)
            case CreatureHitMessage(creature_id=id):
                self.hit.append(id)
            case MachineChangedMessage(machine=machine):
                self.machines[machine.id] = machine
            case PlayerDiedMessage(cause=cause, position=at):
                self.hurt.append(f"{self.world.clock}  Died: {cause}")
                self.died.append(f"{self.world.clock}  Died of {cause} at {self.where}")
                self.where = Point(at.x, at.y, at.map)
                self._reach.clear()
            case ConversationStartedMessage(conversation=talk) if PLAYER_ID in talk.participants:
                self.mine.add(talk.id)
            case LineMessage(line=line) as message if line.conversation_id in self.mine:
                self.heard.append(message)
            case ConversationEndedMessage(conversation_id=id):
                self.ended.add(id)

    def _vitals(self, before: Player, after: Player) -> None:
        if after.health < before.health - 1e-9:
            self.hurt.append(f"{self.world.clock}  Hurt to {after.health:.2f} at {self.where}")
        lamp, now = self._lamp(before), self._lamp(after)
        if lamp.on and not now.on and not now.charge:
            self.dark.append(f"{self.world.clock}  The lamp ran flat at {self.where}")

    @staticmethod
    def _lamp(player: Player) -> Item:
        return next(item for item in player.items if item.kind is ItemKind.LAMP)

    def note(self, what: str) -> None:
        self.notes.append(f"{self.world.clock}  {what} (money {self.money:g})")

    def send(self, message: BaseModel) -> None:
        self.hub.receive(message.model_dump_json())

    async def wait(self, seconds: float) -> None:
        await self.world.loop.run(timedelta(seconds=seconds))

    def join(self, at: Spot) -> None:
        snapshot = self.hub.snapshot()
        self.creatures = {creature.id: creature for creature in snapshot.creatures}
        self.machines = {machine.id: machine for machine in snapshot.machines}
        self.hub.connections.add(self)
        self.move(at)

    async def come_back(self, when: datetime) -> None:
        """Skips the sim time until `when` without ticking it, as if they'd closed the game."""
        self.away += when - self.world.clock.now
        self.world.clock.now = when
        await self.wait(0.1)
        self.note("Came back to the game")

    def kept(self, to: Spot | Point) -> bool:
        """Sends a move to `to`, and says whether the server kept it."""
        there = Point(to.x, to.y, to.map)
        self.light(there)
        self.send(PlayerMoveMessage(position=Position(x=to.x, y=to.y, map=to.map)))
        return self.movement.entities().get(PLAYER_ID) == there

    def move(self, to: Spot | Point) -> None:
        if not self.kept(to):
            raise Refused(f"The server didn't keep the player at {to}")
        self.where = Point(to.x, to.y, to.map)

    def light(self, to: Point) -> None:
        """On in the dark and off in the light, as L does, but never in a bat's sight."""
        lamp = self._lamp(self.player)
        town = self.movement.maps[to.map]
        dark = not town.lit(math.floor(to.x + 0.5), math.floor(to.y + 0.5))
        bats = dark and self.seen_by_bats(to)
        on = dark and bool(lamp.charge) and not bats
        if lamp.on != on:
            self.send(LampMessage(on=on))
        if bats and not self.by_bats:
            self.lamp_off_by_bats += 1
            self.note(f"Kept the lamp off by the bats at {to.map} ({to.x:.0f}, {to.y:.0f})")
        self.by_bats = bats

    def seen_by_bats(self, to: Point) -> bool:
        """Whether a bat could see their lamp at `to`, with nothing solid between."""
        town, chest = self.movement.maps[to.map], (to.x, to.y - 1.0)
        for bat in self.creatures.values():
            at = bat.position
            if bat.kind is CreatureKind.BAT and at.map == to.map:
                eye = (at.x, at.y + 0.5)
                if math.dist(eye, chest) <= BATS and sees(town, eye, chest):
                    return True
        return False

    def doors(self) -> dict[Spot, Spot]:
        """Each door's far end, by where it's taken from: the lift down only once it's open."""
        opened = self.player.lift_open or self.player.body.has(Bionic.DATAJACK)
        return {
            a: b
            for a, b in self.movement.doors.items()
            if opened or b.map != SEWERS or a.map == SEWERS
        }

    def reach(self, jump: Jump | None = None) -> set[Spot]:
        """Everywhere their legs, or `jump`, get to from here, through doors and the lift."""
        legs = jump or jump_of(self.player.body)
        if legs not in self._reach:
            maps, doors = self.movement.maps, self.doors()
            seen, ahead = {self.at}, deque([self.at])
            while ahead:
                spot = ahead.popleft()
                cells = moves(maps[spot.map], (spot.x, spot.y), legs)
                for there in [*(Spot(spot.map, *move.cell) for move in cells), doors.get(spot)]:
                    if there is not None and there not in seen:
                        seen.add(there)
                        ahead.append(there)
            self._reach[legs] = seen
        return self._reach[legs]

    def guarded(self) -> dict[str, set[tuple[int, int]]]:
        """The cells a bot or a dog would see them on, along its floor."""
        found: dict[str, set[tuple[int, int]]] = {}
        for creature in self.creatures.values():
            if (sight := SIGHT.get(creature.kind)) is None:
                continue
            at = creature.position
            row, x = round(at.y), round(at.x)
            cells = found.setdefault(at.map, set())
            cells.update((cx, row) for cx in range(x - round(sight), x + round(sight) + 1))
        return found

    def route(self, goal: Spot, start: Spot | None = None) -> list[Spot] | None:
        """The cheapest way there from here or `start`, out of sight of bots and dogs."""
        if goal not in self.reach() or (start is not None and start not in self.reach()):
            return None
        maps, doors, crossings = self.movement.maps, self.doors(), self.movement.crossings
        legs, guarded, start = jump_of(self.player.body), self.guarded(), start or self.at
        exits: dict[str, list[tuple[int, int]]] = {}
        for end in doors:
            exits.setdefault(end.map, []).append((end.x, end.y))

        def estimate(spot: Spot) -> float:
            if spot.map == goal.map:
                return octile((spot.x, spot.y), (goal.x, goal.y))
            ends = exits.get(spot.map, [])
            return min((octile((spot.x, spot.y), end) + DOOR for end in ends), default=0.0)

        def ways(spot: Spot) -> Iterator[tuple[Spot, float]]:
            if spot in doors:
                yield doors[spot], crossings[spot][1] if spot in crossings else DOOR
            seen = guarded.get(spot.map, set())
            for move in moves(maps[spot.map], (spot.x, spot.y), legs):
                jumps = abs(move.cell[0] - spot.x) + abs(move.cell[1] - spot.y) != 1
                cost = move.cost * (1 + jumps) + JUMPING * jumps
                watched = GUARDED * max(1, abs(move.cell[0] - spot.x)) * (move.cell in seen)
                yield Spot(spot.map, *move.cell), cost + watched

        came: dict[Spot, Spot | None] = {start: None}
        spent = {start: 0.0}
        frontier = [(estimate(start), 0.0, start)]
        while frontier:
            _, so_far, spot = heapq.heappop(frontier)
            if spot == goal:
                found = [spot]
                while (before := came[found[-1]]) is not None:
                    found.append(before)
                return found[::-1]
            if so_far > spent[spot]:
                continue
            for there, step in ways(spot):
                if so_far + step < spent.get(there, math.inf):
                    spent[there], came[there] = so_far + step, spot
                    heapq.heappush(
                        frontier, (so_far + step + estimate(there), so_far + step, there)
                    )
        return None

    async def go(self, goal: Spot) -> None:
        """Runs there by the cheapest way their legs allow, dodging what comes for them."""
        if self.where == Point(goal.x, goal.y, goal.map):
            return
        for _ in range(PLAN):
            route = self.route(goal)
            if route is None:
                raise Refused(f"No way from {self.at} to {goal} on {self.player.body.legs} legs")
            if await self.along(route):
                return
        raise Refused(f"Still dodging on the way to {goal}")

    async def along(self, route: list[Spot]) -> bool:
        """Along `route`, or until they had to dodge something on it."""
        for a, b in pairwise(route):
            if a.map != b.map:
                await self.wait(self.crossing(a))
                self.move(b)
                continue
            if await self.wait_to_come_onto(a, b):
                return False
            for x, y, seconds in self.path(a, b):
                if self.standing() and await self.dodge(b):
                    return False
                await self.wait(seconds)
                self.move(Point(x, y, a.map))
        return True

    def standing(self) -> bool:
        assert self.where is not None
        here, at = self.where, self.at
        town = self.movement.maps[here.map]
        return math.isclose(here.y, at.y) and town.standing(at.x, at.y)

    def step(self, a: Spot, b: Spot) -> float | None:
        """Seconds from `a` to `b` by a step or a climb, or None for a jump."""
        town = self.movement.maps[a.map]
        dx, dy = b.x - a.x, b.y - a.y
        climb = town.climb(a.x, a.y) or town.climb(b.x, b.y)
        if abs(dx) + abs(dy) != 1 and not (climb is DoorKind.STAIRS and abs(dx) == abs(dy) == 1):
            return None
        legs = jump_of(self.player.body)
        pace = CLIMB[climb] * legs.climb if dy and climb is not None else legs.run
        return math.dist((a.x, a.y), (b.x, b.y)) / pace

    def crossing(self, a: Spot) -> float:
        """Seconds through the door at `a`, or up or down to another floor at their legs' climb."""
        kind, tiles = self.movement.crossings.get(a, (DoorKind.DOOR, DOOR))
        seconds = tiles / WALKING_SPEED
        if kind in CLIMB:
            seconds *= CROSSING_SPEED[kind] / (CLIMB[kind] * jump_of(self.player.body).climb)
        return seconds

    def path(self, a: Spot, b: Spot) -> Iterator[tuple[float, float, float]]:
        """The positions they send on the way from `a` to `b`, and the seconds before each."""
        assert self.where is not None
        seconds = self.step(a, b)
        if seconds is None:
            yield from self.arc(a.map, (self.where.x, self.where.y), b)
            return
        n = max(1, math.ceil(seconds / SAMPLE))
        for i in range(1, n + 1):
            yield a.x + (b.x - a.x) * i / n, a.y + (b.y - a.y) * i / n, seconds / n

    def arc(
        self, map: str, start: tuple[float, float], b: Spot | Point
    ) -> Iterator[tuple[float, float, float]]:
        """A jump from `start` to land at `b`, rising as high as they can over the higher end."""
        town, legs = self.movement.maps[map], jump_of(self.player.body)
        (x0, y0), (x1, y1) = start, (b.x, b.y)
        seconds = max(abs(x1 - x0) / legs.run, legs.airtime() * 0.6)
        n = max(2, math.ceil(seconds / SAMPLE))
        for rise in (1.5, 1.2, 0.9, 0.0):
            points = [
                (
                    x0 + (x1 - x0) * i / n,
                    y0 + (y1 - y0) * i / n - rise * 4 * (i / n) * (1 - i / n),
                )
                for i in range(1, n + 1)
            ]
            last = (x0, y0)
            if all(self._clear(town, x, y, last) for x, y in points):
                yield from ((x, y, seconds / n) for x, y in points)
                return
        yield x1, y1, seconds

    @staticmethod
    def _clear(town: TownMap, x: float, y: float, last: tuple[float, float]) -> bool:
        cx = math.floor(x + 0.5)
        return (
            possible(town, x, y, last)
            and not town.solid(cx, math.ceil(round(y, 6)) - 1)
            and not town.solid(cx, math.floor(y - 1.2))
        )

    def others(self, kind: CreatureKind, row: float) -> list[Creature]:
        assert self.where is not None
        return [
            creature
            for creature in self.creatures.values()
            if creature.kind is kind
            and creature.position.map == self.where.map
            and abs(creature.position.y - row) < 0.5
        ]

    async def dodge(self, b: Spot) -> bool:
        """Stomps a rat coming for their food or jumps a bot coming at them: whether they did."""
        assert self.where is not None
        here = self.where
        if self.carries(ItemKind.FOOD):
            rats = [
                rat
                for rat in self.others(CreatureKind.RAT, here.y)
                if rat.state in COMING and abs(rat.position.x - here.x) <= STOMPS
            ]
            if rats:
                await self.stomp(min(rats, key=lambda rat: abs(rat.position.x - here.x)))
                return True
        heading = (b.x > here.x) - (b.x < here.x)
        for bot in self.others(CreatureKind.BOT, here.y):
            ahead = (bot.position.x - here.x) * (heading or 1)
            if heading == 0:
                ahead = abs(ahead)
            if bot.state in COMING and 0 < ahead <= JUMP_OVER:
                way = heading or (1 if bot.position.x > here.x else -1)
                await self.leap(bot, way)
                return True
        return False

    async def stomp(self, rat: Creature) -> None:
        """A hop on the spot, coming down on the rat as it comes under them."""
        assert self.where is not None
        x, row, map = self.where.x, self.where.y, self.where.map
        self.move(Point(x, row - 1, map))
        for _ in range(5):
            await self.wait(SAMPLE)
            now = self.creatures.get(rat.id)
            if now is None or abs(now.position.x - x) <= 0.5:
                break
        now = self.creatures.get(rat.id, rat)
        land = x + max(-0.6, min(0.6, now.position.x - x))
        town = self.movement.maps[map]
        if not town.standing(math.floor(land + 0.5), round(row)):
            land = x
        rats = {id for id, creature in self.creatures.items() if creature.kind is CreatureKind.RAT}
        self.move(Point(land, row, map))
        await self.wait(SAMPLE)
        if gone := sorted(rats - set(self.creatures)):
            self.stomped += len(gone)
            self.note(f"Came down on {', '.join(gone)}")

    async def leap(self, bot: Creature, way: int) -> None:
        """A running jump over a bot, landing well past it, or else away from it."""
        assert self.where is not None
        here, at = self.where, self.at
        town = self.movement.maps[here.map]
        lands = [
            move.cell[0]
            for move in moves(town, (at.x, at.y), jump_of(self.player.body))
            if move.cell[1] == at.y and town.standing(*move.cell)
        ]
        over = [x for x in lands if (x - bot.position.x) * way >= 1.5 and (x - here.x) * way > 0]
        away = [x for x in lands if (x - here.x) * way <= -2]
        if over:
            land, what = min(over, key=lambda x: abs(x - bot.position.x - 3 * way)), "over"
        elif away:
            land, what = max(away, key=lambda x: abs(x - here.x)), "away from"
        else:
            raise Refused(f"Nowhere to jump {bot.id} at {here}")
        for x, y, seconds in self.arc(here.map, (here.x, here.y), Spot(here.map, land, at.y)):
            await self.wait(seconds)
            self.move(Point(x, y, here.map))
        if what == "over":
            self.leapt += 1
        self.note(f"Jumped {what} {bot.id}")

    async def wait_to_come_onto(self, a: Spot, b: Spot) -> bool:
        """Waits off a floor until nothing is by where they'd come onto it: whether they did."""
        town = self.movement.maps[a.map]
        jump = abs(b.x - a.x) + abs(b.y - a.y) != 1 and town.climb(a.x, a.y) is not DoorKind.STAIRS
        off = town.climb(a.x, a.y) is DoorKind.LADDER and town.standing(b.x, b.y)
        if not (jump or off):
            return False

        def waiting() -> bool:
            return any(
                abs(creature.position.x - b.x) <= clear
                for kind, clear in CLEAR.items()
                if kind is not CreatureKind.RAT or self.carries(ItemKind.FOOD)
                for creature in self.others(kind, b.y)
            )

        if not waiting():
            return False
        for _ in range(round(WAITS / SAMPLE)):
            if self.standing():
                await self.dodge(self.at)
            await self.wait(SAMPLE)
            if not waiting():
                break
        self.note(f"Waited at {a} for the way onto {b} to clear")
        return True

    def carries(self, kind: ItemKind) -> bool:
        return any(item.kind is kind for item in self.player.items)

    def plugs(self) -> list[Spot]:
        return [
            Spot(thing.map, thing.stand[0].x, thing.stand[0].y)
            for town in self.movement.maps.values()
            for thing in town.interactables
            if thing.kind is InteractableKind.PLUG
        ]

    def darkness(self, route: list[Spot]) -> float:
        """Seconds of the lamp the way takes, as far as the first plug on it."""
        plugs, legs, spent = set(self.plugs()), jump_of(self.player.body), 0.0
        for a, b in pairwise(route):
            if a in plugs:
                break
            if a.map == b.map and not self.movement.maps[b.map].lit(b.x, b.y):
                seconds = self.step(a, b)
                spent += legs.airtime() if seconds is None else seconds
        return spent

    async def charged(self, goal: Spot) -> None:
        """Charges first if the lamp wouldn't last to `goal` and a plug after, or power is low."""
        route = self.route(goal)
        if route is None:
            return
        back = [self.darkness(way) for plug in self.plugs() if (way := self.route(plug, goal))]
        dark = self.darkness(route) + min(back, default=0.0)
        lamp, power = self._lamp(self.player), self.player.power
        if dark <= (lamp.charge or 0) * LIGHT * 0.8 and power >= 0.5:
            return
        plug = self.at
        if plug not in self.plugs():
            ways = [(len(way), plug) for plug in self.plugs() if (way := self.route(plug))]
            if not ways:
                return
            _, plug = min(ways)
            await self.go(plug)
        for _ in range(100):
            if self.standing() and await self.dodge(plug):
                await self.go(plug)
                continue
            await self.wait(SAMPLE)
            if (self._lamp(self.player).charge or 0) >= 0.999 and self.player.power >= 0.999:
                break
        self.note(f"Charged at {plug}")

    async def to(self, goal: Spot) -> None:
        """`go`, charging first if they need to."""
        await self.charged(goal)
        await self.go(goal)

    def entry(self, place: Id) -> Spot:
        location = self.movement.town.location(place)
        return Spot(location.map, location.entry.x, location.entry.y)

    def lying(self, maps: Collection[str]) -> list[tuple[Pickup, Pile]]:
        """What lies at the pickups on `maps` now, as `player_state` shows it."""
        piles = {(pile.at.map, pile.at.x, pile.at.y): pile for pile in self.state.piles}
        return [
            (pickup, piles[(pickup.map, pickup.x, pickup.y)])
            for name in maps
            for pickup in self.movement.maps[name].pickups
            if (pickup.map, pickup.x, pickup.y) in piles
        ]

    def away_from(self, x: int, map: str) -> float:
        """Roughly how far: along this map, or further on another."""
        here = abs(x - self.at.x)
        return here if map == self.at.map else 1000 + here

    def fits(self, items: Collection[Item]) -> bool:
        weight = sum(item.load for item in items)
        return weight <= self.player.carry_limit - self.player.load + 1e-9

    async def take(self, pickup: Pickup) -> None:
        emptied = self.player.taken.get(pickup.id)
        await self.to(Spot(pickup.map, pickup.x, pickup.y))
        if self.player.taken.get(pickup.id) != emptied:
            self.note(f"Something had taken what lay at {pickup.id} before they got there")
            return
        money, items = self.money, list(self.player.items)
        self.send(PickUpMessage())
        if (self.money, self.player.items) == (money, items):
            raise Refused(f"Nothing was picked up at {pickup.id}")
        taken = self.gained(items)
        found = [f"{self.money - money:g} in cash"] if self.money > money else []
        self.note(f"Picked up {', '.join([*found, *taken])} at {pickup.id}")

    def gained(self, before: Sequence[Item]) -> list[str]:
        """The names of what's new since `before`, a stack that's grown among them."""
        now = self.player.items
        grown = [item.name for item, was in zip(now, before, strict=False) if item != was]
        return [*grown, *(item.name for item in now[len(before) :])]

    def thing(self, id: Id) -> Interactable:
        towns = self.movement.maps.values()
        return next(thing for town in towns for thing in town.interactables if thing.id == id)

    async def search(self, id: Id) -> None:
        """E at something to search: what it holds, and the recipe it teaches."""
        thing = self.thing(id)
        if not self.fits(thing.items):
            await self.sell()
        stands = [Spot(thing.map, tile.x, tile.y) for tile in thing.stand]
        await self.to(next(spot for spot in stands if spot in self.reach()))
        items, known = list(self.player.items), list(self.player.mind.recipes)
        self.send(PickUpMessage())
        if id not in self.player.searched:
            raise Refused(f"{id} wasn't searched")
        found = self.gained(items)
        found += [
            f"the {bionic} recipe" for bionic in self.player.mind.recipes if bionic not in known
        ]
        self.note(f"Searched {id}: {', '.join(found) or 'nothing'}")

    def wanted(self) -> Counter[str]:
        """The parts the recipes they know but haven't had fitted use up, and a broken machine's."""
        wanted: Counter[str] = Counter()
        for recipe in self.state.recipes:
            if not self.player.body.has(recipe.bionic):
                wanted.update(recipe.parts)
        for machine in self.machines.values():
            wanted.update(machine.parts)
        return wanted

    def recycling(self) -> bool:
        recycler = self.machines.get("recycler")
        return recycler is not None and recycler.state is MachineState.WORKING

    def spare(self) -> list[Item]:
        """What they carry that a buyer takes and nothing they know needs, or the recycler would
        press once it works."""
        keep, spare = self.wanted(), []
        for item in self.player.items:
            if item.kind not in (ItemKind.SALVAGE, ItemKind.PART):
                continue
            if self.recycling() and item.id in SCRAP:
                continue
            if keep[item.id]:
                keep[item.id] -= 1
            else:
                spare.append(item)
        return spare

    async def sell(self) -> None:
        """Sells what they carry that they don't need, at the nearest buyer."""
        ways = [(len(way), place) for place in BUYERS if (way := self.route(self.entry(place)))]
        _, place = min(ways)
        await self.to(self.entry(place))
        money = self.money
        for item in self.spare():
            self.send(SellMessage(item=item.id))
        if self.money <= money:
            raise Refused(f"Nothing sold at {place}")
        self.note(f"Sold what they didn't need at {place} for {self.money - money:g}")

    async def fed(self) -> None:
        """Goes home and eats, once they're hungry."""
        if self.player.hunger < HUNGRY:
            return
        await self.to(self.entry(HOME))
        hunger = self.player.hunger
        self.send(EatMessage(item=None))
        if self.player.hunger >= hunger:
            raise Refused("They couldn't eat at home")
        self.note(f"Ate at home, hunger {hunger:.2f}")

    async def clinic(self) -> None:
        await self.to(self.entry("clinic"))

    def price(self, bionic: Bionic) -> float:
        fittings = self.state.buyer.fittings if self.state.buyer else []
        fitting = next((f for f in fittings if f.bionic is bionic), None)
        if fitting is None:
            raise Refused(f"The clinic doesn't offer {bionic} to {self.player.body}")
        return fitting.price

    async def sell_part(self, part: BodyPart) -> None:
        price = self.state.buyer.parts.get(part) if self.state.buyer else None
        self.send(SellPartMessage(part=part))
        await self.wait(0.1)
        if price is None or getattr(self.player.body, part) != SOLD:
            raise Refused(f"The clinic didn't buy their {part}")
        self.note(f"Sold their {part.replace('_', ' ')} for {price:g}")

    async def sell_recipes(self) -> None:
        """Sells the clinic each recipe she'd buy."""
        for bionic, price in (self.state.buyer.recipes if self.state.buyer else {}).items():
            self.send(SellRecipeMessage(recipe=bionic))
            await self.wait(0.1)
            if bionic not in self.player.mind.sold:
                raise Refused(f"The clinic didn't buy the {bionic} recipe")
            self.note(f"Sold the {bionic} recipe for {price:g}")

    async def fit(self, bionic: Bionic, part: BodyPart) -> None:
        price = self.price(bionic)
        self.send(FitMessage(bionic=bionic, part=part))
        await self.wait(0.1)
        if getattr(self.player.body, part) != bionic:
            raise Refused(f"The clinic didn't fit {bionic} for {price:g}: {self.player}")
        self._reach.clear()
        self.note(f"Had {bionic.replace('_', ' ')} fitted for {price:g}")

    async def find(self, at: Spot) -> list[str]:
        """E at a clue or a jack: the facts the journal gains."""
        await self.to(at)
        known = {entry.fact_id for entry in self.journal}
        self.send(PickUpMessage())
        found = [entry.fact_id for entry in self.journal if entry.fact_id not in known]
        self.note(f"Found {', '.join(found) or 'nothing'} at {at.map} ({at.x}, {at.y})")
        return found

    def awake(self, npc: Id) -> bool:
        return self.behaviour.goal(npc).activity is not Activity.SLEEP

    def beside(self, there: Spot | Point, by: tuple[int, ...] = (1, 2)) -> Spot:
        """A cell to stand on along the row from `there`, nearest first, or `there` itself."""
        town, x, y = self.movement.maps[there.map], round(there.x), round(there.y)
        cells = [(x + dx, y) for d in by for dx in (-d, d) if town.standing(x + dx, y)]
        return Spot(there.map, *(cells[0] if cells else (x, y)))

    async def approach(self, npc: Id) -> bool:
        """Runs up beside `npc`, following them a few times if they walk off."""
        for _ in range(FOLLOW):
            await self.to(self.beside(self.movement.position(npc)))
            if between(self.movement, npc, PLAYER_ID) <= NEAR:
                return True
        return False

    async def say(self, npc: Id, text: str, seconds: int = 60) -> tuple[list[LineMessage], bool]:
        """Says `text` to `npc`: their lines back, and whether the conversation ended."""
        self.heard.clear()
        self.send(PlayerSayMessage(text=text, target=npc))
        said, still = 0, 0
        for _ in range(seconds):
            await self.wait(1)
            lines = [m for m in self.heard if m.line.speaker == npc]
            ended = any(m.line.conversation_id in self.ended for m in lines)
            still = still + 1 if lines and len(lines) == said else 0
            said = len(lines)
            if ended or still >= QUIET:
                break
        self.note(f"Said {text!r} to {npc}, who said {' '.join(m.line.text for m in lines)!r}")
        return lines, ended

    def stand_at(self, id: Id) -> Spot:
        """A stand tile of the thing `id` that they can get to."""
        thing = self.thing(id)
        stands = [Spot(thing.map, tile.x, tile.y) for tile in thing.stand]
        return next(spot for spot in stands if spot in self.reach())

    async def repair(self, machine: Id) -> None:
        """E at a broken machine, with every part it needs."""
        await self.to(self.stand_at(machine))
        self.send(RepairMessage(machine=machine))
        await self.wait(SAMPLE)
        if self.machines[machine].state is not MachineState.WORKING:
            raise Refused(f"The {machine} wasn't repaired: {self.machines[machine]}")
        self.note(f"Repaired the {machine}")

    async def make(self, machine: Id, item: Id) -> None:
        """Has a working machine make `item`, standing at it."""
        await self.to(self.stand_at(machine))
        before = list(self.player.items)
        self.send(MakeMessage(machine=machine, item=item))
        await self.wait(SAMPLE)
        if self.player.items == before:
            raise Refused(f"The {machine} didn't make {item}: {self.player.items}")
        names = {i.id: i.name for i in self.player.items}
        made = amounts(self.player.items) - amounts(before)
        what = [f"{names[id]} ×{n:g}" for id, n in made.items()]
        self.note(f"The {machine} made {', '.join(what)}")

    def weapon(self) -> Item | None:
        return next((item for item in self.player.items if item.kind is ItemKind.WEAPON), None)

    def loaded(self) -> int:
        weapon = self.weapon()
        return (weapon.rounds or 0) if weapon else 0

    def spare_rounds(self) -> int:
        return round(sum(i.amount for i in self.player.items if i.kind is ItemKind.ROUNDS))

    async def reload(self) -> None:
        loaded = self.loaded()
        self.send(ReloadMessage())
        await self.wait(SAMPLE)
        if self.loaded() <= loaded:
            raise Refused(f"Nothing was loaded into {self.weapon()}")
        self.note(f"Loaded {self.loaded() - loaded} rounds, {self.spare_rounds()} spare")

    def in_line(self, kind: CreatureKind) -> tuple[Creature, SideFacing] | None:
        """The nearest creature of `kind` that a shot from here would hit, as the server aims it,
        and the way to face it."""
        assert self.where is not None
        here, (x, feet) = self.where, (self.at.x, self.at.y)
        town = self.movement.maps[here.map]
        for way, facing in ((1, SideFacing.EAST), (-1, SideFacing.WEST)):
            rows = {feet, feet - 1}
            for column in range(x, x + way * (RANGE + 1), way):
                rows = {row for row in rows if not town.solid(column, row)}
                if not rows:
                    break
                there = [
                    c
                    for c in self.creatures.values()
                    if c.position.map == here.map
                    and (c.position.x - here.x) * way >= 0
                    and round(c.position.x) == column
                    and math.ceil(round(c.position.y, 6)) in rows
                ]
                if there:
                    nearest = min(there, key=lambda c: abs(c.position.x - here.x))
                    if nearest.kind is kind:
                        return nearest, facing
                    break
        return None

    async def fire(self, facing: SideFacing) -> Id | None:
        """A shot the way they face: the creature it put down, if any."""
        hits, alive = len(self.hit), {id: c.kind for id, c in self.creatures.items()}
        self.send(FireMessage(facing=facing))
        await self.wait(SAMPLE)
        gone = [id for id in self.hit[hits:] if id in alive and id not in self.creatures]
        for id in gone:
            self.shot[alive[id]] += 1
            self.note(f"Shot {id} down, {self.loaded()} rounds left in the pistol")
        return gone[0] if gone else None

    async def shoot(self, kind: CreatureKind, count: int, seconds: float = 60.0) -> None:
        """Shoots each creature of `kind` that comes in line from here until `count` are down."""
        down = self.shot[kind]
        for _ in range(round(seconds / SAMPLE)):
            if self.shot[kind] - down >= count:
                return
            if not self.loaded():
                await self.reload()
            if (target := self.in_line(kind)) is not None:
                await self.fire(target[1])
                continue
            if self.standing():
                await self.dodge(self.at)
            await self.wait(SAMPLE)
        raise Refused(f"Shot {self.shot[kind] - down} of {count} {kind}s in {seconds:g} s")

    async def store(self, *ids: Id) -> None:
        """Puts each of `ids` they carry in the lockers."""
        await self.to(self.stand_at(LOCKERS))
        for id in ids:
            before = list(self.player.items)
            self.send(StashMessage(item=id, action="store"))
            await self.wait(SAMPLE)
            if self.player.items == before:
                raise Refused(f"The lockers didn't take {id}")
        self.note(f"Stored {', '.join(ids)} in the lockers")

    async def take_out(self, *ids: Id) -> None:
        """Takes each of `ids` out of the lockers."""
        await self.to(self.stand_at(LOCKERS))
        for id in ids:
            before = list(self.player.items)
            self.send(StashMessage(item=id, action="take"))
            await self.wait(SAMPLE)
            if self.player.items == before:
                raise Refused(f"{id} didn't come out of the lockers")
        self.note(f"Took {', '.join(ids)} out of the lockers")

    def corpse(self, id: Id) -> Corpse | None:
        return next((corpse for corpse in self.player.corpses if corpse.id == id), None)

    def room(self) -> float:
        return self.player.carry_limit - self.player.load + 1e-9

    async def salvage(self, id: Id) -> list[str]:
        """E at their corpse: the money, then each bionic and item that fits, one at a time."""
        corpse = self.corpse(id)
        assert corpse is not None
        await self.to(Spot(corpse.at.map, corpse.at.x, corpse.at.y))
        taken: list[str] = []
        if corpse.money:
            await self._take(TakeMessage(corpse=id, pile=None, item=None, index=None, bionic=None))
            taken.append(f"{corpse.money:g} in cash")
        while (corpse := self.corpse(id)) is not None:
            weights = {item.bionic: item.weight for item in self.state.bionics}
            bionic = next((b for b in corpse.bionics if weights[b] <= self.room()), None)
            index = next((i for i, it in enumerate(corpse.items) if it.load <= self.room()), None)
            if bionic is not None:
                await self._take(
                    TakeMessage(corpse=id, pile=None, item=None, index=None, bionic=bionic)
                )
                taken.append(bionic.replace("_", " "))
            elif index is not None:
                item = corpse.items[index]
                await self._take(
                    TakeMessage(corpse=id, pile=None, item=item.id, index=index, bionic=None)
                )
                taken.append(item.name)
            else:
                break
        left = "and it's gone" if self.corpse(id) is None else "leaving what didn't fit"
        self.note(f"Salvaged {', '.join(taken)} from {id}, {left}")
        return taken

    async def haul(self, at: MapTile) -> list[str]:
        """E at a pile of theirs, such as a bot's haul: each thing in it that fits."""
        await self.to(Spot(at.map, at.x, at.y))
        taken: list[str] = []
        while (pile := next((p for p in self.player.left if p.at == at), None)) is not None:
            index = next((i for i, it in enumerate(pile.items) if it.load <= self.room()), None)
            if pile.money:
                await self._take(
                    TakeMessage(corpse=None, pile=at, item=None, index=None, bionic=None)
                )
                taken.append(f"{pile.money:g} in cash")
            elif index is not None:
                item = pile.items[index]
                await self._take(
                    TakeMessage(corpse=None, pile=at, item=item.id, index=index, bionic=None)
                )
                taken.append(item.name)
            else:
                break
        self.note(
            f"Took {', '.join(taken) or 'nothing'} from what lay at {at.map} ({at.x}, {at.y})"
        )
        return taken

    async def _take(self, message: TakeMessage) -> None:
        before = (self.money, list(self.player.items))
        self.send(message)
        await self.wait(SAMPLE)
        if (self.money, self.player.items) == before:
            raise Refused(f"Nothing came of {message!r}")
