import json
import math
import random
import sqlite3
import sys
from collections import deque
from collections.abc import AsyncGenerator, Collection, Mapping
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from pydantic import BaseModel
from starlette.applications import Starlette

from simile.behaviour import Activity
from simile.conversation.prompt import CUES, Cue
from simile.conversation.telling import Stance, Telling
from simile.economy import PLAYER, Kind
from simile.llm import LLMClient
from simile.llm.fake import FakeProvider
from simile.llm.lifespan import CannedProvider
from simile.llm.provider import Request, Usage
from simile.loop import stand_in
from simile.persistence import investigation_of, player_of
from simile.player.config import DEFAULT_CONFIG as PLAYER_CONFIG
from simile.protocol import (
    ConversationEndedMessage,
    ConversationStartedMessage,
    EatMessage,
    FitMessage,
    JournalMessage,
    LampMessage,
    LineMessage,
    PickUpMessage,
    PlayerMoveMessage,
    PlayerSayMessage,
    PlayerStateMessage,
    Position,
    SellMessage,
    SellPartMessage,
    hub_of,
)
from simile.protocol.messages import server_messages
from simile.reflection.extraction import SYSTEM as REFLECTING
from simile.schema import (
    PLAYER_ID,
    SOLD,
    Bionic,
    BodyPart,
    Id,
    Incident,
    InteractableKind,
    ItemKind,
    JournalEntry,
    MemoryKind,
    Pile,
    Player,
)
from simile.sim import Clock, FakeWallClock, World, world_of
from simile.social.bionics import TOPIC as BIONICS
from simile.social.bionics import tolerance
from simile.social.config import DEFAULT_BIONICS
from simile.story import NOTES, load_story, says
from simile.story.content import HATCH, TERMINAL
from simile.story.incident import HATCH_LOG, LIFT_LOG, NOTED, THERE, there
from simile.street.jump import JUMP, RUN_SPEED, Jump, jump_of
from simile.street.sewers import SEWERS
from simile.voicing.distance import between
from simile.world import Point, movement_of
from simile.world.map import WALKING_SPEED, Pickup, PickupKind
from simile.world.paths import DOOR, Spot, find_route, steps

START = datetime(2026, 10, 19, 8, tzinfo=UTC)
WORLD = "world.db"
SQUARE, HOME, CLINIC = "square", "maker_space", "clinic"
BUYERS = (CLINIC, "scrap_stall")
OUTSIDE_THE_CLINIC = Spot("metro", 87, 15)
"""Two cells short of the clinic's door, where the browser's beats at the clinic start."""
LIFT = Spot("metro", 100, 15)
LANDING = Spot(SEWERS, 2, 15)
HUNGRY = 0.5
MORNING = 9
DAYS = 7
"""The most days of salvage rounds the eye may take."""
NEAR = 2.0
"""How near a resident, in tiles along the street, the player walks up before talking."""
FOLLOW = 4
QUIET = 10
"""Sim seconds without a line before a reply is over: longer than a goodbye waits for an answer."""
QUESTION = "Where were you the night Aris was attacked?"
HELLO = "Hello there! Lovely day for it."
REFUSAL = CUES[Cue.REFUSE].split("{other}")[0]
SKIPPED = ('{"type":"entity_moved"', '{"type":"clock"', '{"type":"npc_state"')


def alibis(incident: Incident | None) -> dict[str, str]:
    """Each attacker's direction to lie about where they'd been, and the alibi it has them give."""
    found = {}
    for fact in incident.facts if incident else []:
        for knower in fact.known_by if fact.id.startswith(THERE) else []:
            if knower.cover:
                telling = Telling(fact, knower, Stance.LIE, fact.what)
                found[telling.temptation().direction()] = knower.cover
    return found


class Covers:
    """The canned fake LLM, but an attacker asked where they'd been gives their alibi exactly."""

    name = "covers"

    def __init__(self, alibis: Mapping[str, str]) -> None:
        self.alibis = dict(alibis)
        self.canned = CannedProvider()
        self.refusals: list[str] = []
        """Each prompt that cued a resident to turn the player down."""

    def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        prompt = "\n".join(message.content for message in request.messages)
        if REFUSAL in prompt:
            self.refusals.append(prompt)
        alibi = next((cover for say, cover in self.alibis.items() if say in prompt), None)
        if alibi is not None:
            return FakeProvider([alibi]).stream(request)
        if request.system.startswith(REFLECTING):
            return FakeProvider(['{"reflections": []}']).stream(request)
        return self.canned.stream(request)


class Refused(Exception):
    """The server didn't do what the player's message asked."""


class LoopPlayer:
    """A client in the game that plays by the client's messages, and knows only what it's sent."""

    def __init__(self, app: Starlette, notes: list[str]) -> None:
        self.hub, self.world, self.movement = hub_of(app), world_of(app), movement_of(app)
        self.behaviour = app.state.behaviour
        self.notes = notes
        self.state = PlayerStateMessage(player=Player())
        self.journal: list[JournalEntry] = []
        self.mine: set[str] = set()
        """The conversations with the player."""
        self.heard: deque[LineMessage] = deque(maxlen=200)
        self.ended: set[str] = set()
        self.at: Spot | None = None
        self.away = timedelta()
        """Sim time skipped while out of the game."""
        self._reach: dict[Jump, set[Spot]] = {}

    @property
    def player(self) -> Player:
        return self.state.player

    @property
    def money(self) -> float:
        return self.player.money

    def put(self, frame: str | bytes) -> None:
        if isinstance(frame, bytes) or frame.startswith(SKIPPED):
            return
        match server_messages.validate_json(frame):
            case PlayerStateMessage() as state:
                self.state = state
            case JournalMessage(entries=entries):
                self.journal = entries
            case ConversationStartedMessage(conversation=talk) if PLAYER_ID in talk.participants:
                self.mine.add(talk.id)
            case LineMessage(line=line) as message if line.conversation_id in self.mine:
                self.heard.append(message)
            case ConversationEndedMessage(conversation_id=id):
                self.ended.add(id)

    def note(self, what: str) -> None:
        self.notes.append(f"{self.world.clock}  {what} (money {self.money:g})")

    def send(self, message: BaseModel) -> None:
        self.hub.receive(message.model_dump_json())

    async def wait(self, seconds: float) -> None:
        await self.world.loop.run(timedelta(seconds=seconds))

    def join(self, at: Spot) -> None:
        self.hub.connections.add(self)
        self.move(at)

    async def come_back(self, when: datetime) -> None:
        """Skips the sim time until `when` without ticking it, as if they'd closed the game."""
        self.away += when - self.world.clock.now
        self.world.clock.now = when
        await self.wait(0.1)
        self.note("Came back to the game")

    def kept(self, to: Spot) -> bool:
        """Sends a move to `to`, and says whether the server kept it."""
        self.light(to)
        self.send(PlayerMoveMessage(position=Position(x=to.x, y=to.y, map=to.map)))
        return self.movement.entities().get(PLAYER_ID) == Point(to.x, to.y, to.map)

    def move(self, to: Spot) -> None:
        if not self.kept(to):
            raise Refused(f"The server didn't keep the player at {to}")
        self.at = to

    def light(self, to: Spot) -> None:
        """Switches the lamp on going into the dark and off coming out, as L does."""
        lamp = next((item for item in self.player.items if item.kind is ItemKind.LAMP), None)
        dark = not self.movement.maps[to.map].lit(to.x, to.y)
        if lamp is not None and lamp.on != dark and (lamp.charge or not dark):
            self.send(LampMessage(on=dark))

    def reach(self, jump: Jump | None = None) -> set[Spot]:
        """Everywhere their legs, or `jump`, get to from here, through doors and the lift."""
        legs = jump or jump_of(self.player.body)
        if legs not in self._reach:
            assert self.at is not None
            maps, doors = self.movement.maps, self.movement.doors
            seen, ahead = {self.at}, deque([self.at])
            while ahead:
                spot = ahead.popleft()
                cells = steps(maps[spot.map], (spot.x, spot.y), legs)
                for there in [*(Spot(spot.map, *cell) for cell, _ in cells), doors.get(spot)]:
                    if there is not None and there not in seen:
                        seen.add(there)
                        ahead.append(there)
            self._reach[legs] = seen
        return self._reach[legs]

    def route(self, goal: Spot) -> list[Spot] | None:
        assert self.at is not None
        if goal not in self.reach():
            return None
        movement, legs = self.movement, jump_of(self.player.body)
        return find_route(
            movement.maps, self.at, goal, movement.doors, movement.crossings, jumps=legs
        )

    async def go(self, goal: Spot) -> None:
        """Runs there by the shortest way their legs allow."""
        route = self.route(goal)
        if route is None:
            raise Refused(f"No way from {self.at} to {goal} on {self.player.body.legs} legs")
        for a, b in pairwise(route):
            if a.map == b.map:
                seconds = math.dist((a.x, a.y), (b.x, b.y)) / RUN_SPEED
            else:
                seconds = self.movement.crossings.get(a, (None, DOOR))[1] / WALKING_SPEED
            await self.wait(seconds)
            self.move(b)

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

    def away_from(self, pickup: Pickup) -> float:
        """Roughly how far: along this map, or further on another."""
        assert self.at is not None
        here = abs(pickup.x - self.at.x) + abs(pickup.y - self.at.y)
        return here if pickup.map == self.at.map else 1000 + here

    def fits(self, pile: Pile) -> bool:
        weight = sum(item.weight for item in pile.items)
        return weight <= self.player.carry_limit - self.player.load + 1e-9

    async def take(self, pickup: Pickup) -> None:
        await self.go(Spot(pickup.map, pickup.x, pickup.y))
        money, items = self.money, len(self.player.items)
        self.send(PickUpMessage())
        if (self.money, len(self.player.items)) == (money, items):
            raise Refused(f"Nothing was picked up at {pickup.id}")
        taken = [item.name for item in self.player.items[items:]]
        found = [f"{self.money - money:g} in cash"] if self.money > money else []
        self.note(f"Picked up {', '.join([*found, *taken])} at {pickup.id}")

    def carrying(self) -> bool:
        return any(item.kind is ItemKind.SALVAGE for item in self.player.items)

    async def sell(self) -> None:
        """Sells all the salvage they carry, at the nearest buyer."""
        ways = [(len(way), place) for place in BUYERS if (way := self.route(self.entry(place)))]
        _, place = min(ways)
        await self.go(self.entry(place))
        money = self.money
        self.send(SellMessage(item=None))
        if self.money <= money:
            raise Refused(f"Nothing sold at {place}")
        self.note(f"Sold salvage at {place} for {self.money - money:g}")

    async def gather(self, maps: Collection[str], enough: float = math.inf) -> None:
        """Picks up what pays on `maps`, nearest first, selling when nothing more fits."""
        while self.money < enough:
            await self.fed()
            near = [
                (self.away_from(pickup), pickup.id, pickup)
                for pickup, pile in self.lying(maps)
                if (pile.money or any(item.kind is ItemKind.SALVAGE for item in pile.items))
                and Spot(pickup.map, pickup.x, pickup.y) in self.reach()
                and self.fits(pile)
            ]
            if near:
                await self.take(min(near)[2])
            elif self.carrying():
                await self.sell()
            else:
                return

    async def fed(self) -> None:
        """Goes home and eats, once they're hungry."""
        if self.player.hunger < HUNGRY:
            return
        await self.go(self.entry(HOME))
        hunger = self.player.hunger
        self.send(EatMessage(item=None))
        if self.player.hunger >= hunger:
            raise Refused("They couldn't eat at home")
        self.note(f"Ate at home, hunger {hunger:.2f}")

    async def clinic(self) -> None:
        await self.go(self.entry(CLINIC))

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

    async def fit(self, bionic: Bionic, part: BodyPart) -> None:
        price = self.price(bionic)
        self.send(FitMessage(bionic=bionic, part=part))
        await self.wait(0.1)
        if getattr(self.player.body, part) != bionic:
            raise Refused(f"The clinic didn't fit {bionic} for {price:g}")
        self.note(f"Had {bionic.replace('_', ' ')} fitted for {price:g}")

    async def find(self, at: Spot) -> list[str]:
        """E at a clue or a jack: the facts the journal gains."""
        await self.go(at)
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
            await self.go(self.beside(self.movement.position(npc)))
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


class Saves:
    """The world before each browser beat: its database, and where the beat starts, in JSON."""

    def __init__(self, app: Starlette, folder: Path | None) -> None:
        self.app = app
        self.folder = folder

    async def write(self, beat: str, player: LoopPlayer, **extra: object) -> None:
        if self.folder is None:
            return
        assert player.at is not None
        await self.app.state.persistence.save()
        world = sqlite3.connect(self.folder / WORLD)
        copy = sqlite3.connect(self.folder / f"{beat}.db")
        with closing(world), closing(copy):
            world.backup(copy)
        at = player.at
        info = {
            "at": {"map": at.map, "x": at.x, "y": at.y},
            "time": player.world.clock.now.isoformat(),
            "money": player.money,
            **extra,
        }
        (self.folder / f"{beat}.json").write_text(json.dumps(info, indent=2) + "\n")
        player.note(f"Saved the {beat} beat")


@dataclass
class Result:
    start: datetime
    end: datetime
    away: timedelta
    notes: list[str]
    player: Player
    journal: list[JournalEntry]
    attacker: Id
    lie: LineMessage
    refused_by: Id
    seen_by: dict[Id, list[str]]
    earned: dict[Kind, float] = field(default_factory=dict)
    """The player's money in and out of the ledger by kind: out is negative."""

    @property
    def days(self) -> float:
        return (self.end - self.start) / timedelta(days=1)

    @property
    def played(self) -> timedelta:
        return self.end - self.start - self.away


class Playthrough:
    """The six beats of S15, played in order."""

    def __init__(self, app: Starlette, covers: Covers, saves: Saves) -> None:
        self.app, self.covers, self.saves = app, covers, saves
        self.notes: list[str] = []
        self.player = LoopPlayer(app, self.notes)
        self.incident = investigation_of(app).incident
        assert self.incident is not None

    def pickup(self, id: Id) -> Pickup:
        towns = self.player.movement.maps.values()
        return next(pickup for town in towns for pickup in town.pickups if pickup.id == id)

    def jack(self, id: Id) -> Spot:
        towns = self.player.movement.maps.values()
        jack = next(item for town in towns for item in town.interactables if item.id == id)
        assert jack.kind is InteractableKind.JACK
        return Spot(jack.map, jack.stand[0].x, jack.stand[0].y)

    async def run(self) -> Result:
        start = self.player.world.clock.now
        await self.sell_a_kidney()
        await self.legs_and_a_secret()
        await self.datajack_and_the_lift()
        await self.the_sewers_clue()
        attacker, lie = await self.the_eye_and_a_lie()
        refused_by, seen_by = await self.residents_react()
        ledger = self.app.state.economy.ledger
        earned: dict[Kind, float] = {}
        for entry in ledger.entries:
            if PLAYER in (entry.payer, entry.payee):
                sign = 1 if entry.payee == PLAYER else -1
                earned[entry.kind] = earned.get(entry.kind, 0.0) + sign * entry.amount
        p = self.player
        return Result(
            start,
            p.world.clock.now,
            p.away,
            self.notes,
            p.player,
            p.journal,
            attacker,
            lie,
            refused_by,
            seen_by,
            earned,
        )

    async def sell_a_kidney(self) -> None:
        p = self.player
        p.join(p.entry(SQUARE))
        await p.go(OUTSIDE_THE_CLINIC)
        await self.saves.write("kidney", p)
        await p.clinic()
        await p.sell_part("left_kidney")

    async def legs_and_a_secret(self) -> None:
        p, ledge = self.player, self.pickup("metro_secret_ledge")
        if Spot(ledge.map, ledge.x, ledge.y) in p.reach(JUMP):
            raise Refused("The high ledge is in reach on the player's own legs")
        await p.fit(Bionic.HYDRAULIC_LEGS, "legs")
        await p.take(ledge)

    async def datajack_and_the_lift(self) -> None:
        p = self.player
        stand_in.learn(player_of(self.app), Bionic.DATAJACK)
        await p.clinic()
        await p.gather({"metro"}, enough=p.price(Bionic.DATAJACK))
        await p.go(LIFT)
        if p.kept(LANDING):
            raise Refused("The server let the player into the sewers without the datajack")
        p.note("The lift didn't take them without the datajack")
        await p.go(OUTSIDE_THE_CLINIC)
        stand_in.carry(player_of(self.app), Bionic.DATAJACK)
        await p.wait(0.1)
        await self.saves.write("datajack", p, lift_log=self.fact(LIFT_LOG))
        await p.clinic()
        await p.fit(Bionic.DATAJACK, "vertebra")
        if LIFT_LOG not in await p.find(self.jack(TERMINAL)):
            raise Refused("The dead terminal held no clue")
        await p.go(LANDING)

    async def the_sewers_clue(self) -> None:
        p, hatch = self.player, self.jack(HATCH)
        if hatch in p.reach(JUMP):
            raise Refused("The hatch is in reach on the player's own legs")
        await p.go(p.beside(hatch, (2, 3)))
        await self.saves.write("hatch", p, hatch_log=self.fact(HATCH_LOG))
        if HATCH_LOG not in await p.find(hatch):
            raise Refused("The hatch held no clue")
        await p.gather({SEWERS})
        if p.at and p.at.map != "metro":
            await p.go(LIFT)
        p.note("Back up in the metro")

    async def the_eye_and_a_lie(self) -> tuple[Id, LineMessage]:
        p = self.player
        stand_in.learn(player_of(self.app), Bionic.INFRARED_EYE)
        stand_in.carry(player_of(self.app), Bionic.INFRARED_EYE)
        await p.clinic()
        price = p.price(Bionic.INFRARED_EYE)
        for _ in range(DAYS):
            await p.gather({"metro", SEWERS}, enough=price)
            if p.money >= price:
                break
            await p.come_back(self.salvage_back())
        else:
            raise Refused(f"{DAYS} days of salvage didn't pay for the eye")
        await p.clinic()
        await p.fit(Bionic.INFRARED_EYE, "left_eye")
        attacker = await self.find_attacker()
        alibi = self.alibi(attacker)
        name = self.player.behaviour.npcs[attacker].name
        await self.saves.write("eye", p, attacker={"id": attacker, "name": name}, alibi=alibi)
        lines, _ = await p.say(attacker, QUESTION)
        lie = next((line for line in lines if line.flushed), None)
        if lie is None or not says(" ".join(m.line.text for m in lines), alibi):
            raise Refused(f"{attacker}'s alibi didn't flush: {lines}")
        entry = next((e for e in p.journal if e.fact_id == there(attacker)), None)
        if entry is None or entry.flushed is not True:
            raise Refused(f"The journal didn't record {attacker}'s lie as flushed: {entry}")
        return attacker, lie

    async def residents_react(self) -> tuple[Id, dict[Id, list[str]]]:
        p = self.player
        clue = next(clue for clue in load_story().clues if clue.id == NOTES)
        if NOTED not in await p.find(Spot(clue.map, clue.x, clue.y)):
            raise Refused("Aris's notes held no clue")
        refused_by = await self.turned_down()
        return refused_by, self.seen_by()

    async def turned_down(self) -> Id:
        """Talks to the residents most against bionics until one turns the player down."""
        p, npcs = self.player, self.player.behaviour.npcs
        against = sorted((tolerance(npc.values), id) for id, npc in npcs.items())
        for feeling, npc in against:
            if feeling > -DEFAULT_BIONICS.mildly or not p.awake(npc):
                continue
            if not await p.approach(npc):
                continue
            refusals = len(self.covers.refusals)
            _, ended = await p.say(npc, HELLO)
            if ended and len(self.covers.refusals) > refusals:
                p.note(f"{npc} turned them down")
                return npc
        raise Refused("Nobody turned the player down")

    def seen_by(self) -> dict[Id, list[str]]:
        """Each resident's memories of seeing the player's bionics."""
        memory, now = self.app.state.memory, self.player.world.clock.now
        seen = {}
        for npc in self.player.behaviour.npcs:
            memories = memory.recall(
                npc, now, about=PLAYER_ID, kind=MemoryKind.OBSERVATION, k=sys.maxsize
            )
            if sightings := [m.content for m in memories if BIONICS in m.topics]:
                seen[npc] = sightings
        return seen

    async def find_attacker(self) -> Id:
        """The first attacker the player finds awake and walks up to, once they've settled."""
        p, engine = self.player, self.app.state.conversation
        assert self.incident is not None
        for _ in range(3):
            for attacker in self.incident.attackers:
                if not p.awake(attacker) or not await p.approach(attacker):
                    continue
                for _ in range(60):
                    mind = p.behaviour.minds[attacker]
                    if mind.walk is None and not engine.talking(attacker):
                        break
                    await p.wait(5)
                if await p.approach(attacker):
                    return attacker
            await p.come_back(self.morning())
        raise Refused("No attacker could be found")

    def alibi(self, attacker: Id) -> str:
        assert self.incident is not None
        fact = next(fact for fact in self.incident.facts if fact.id == there(attacker))
        knower = next(knower for knower in fact.known_by if knower.id == attacker)
        assert knower.cover is not None
        return knower.cover

    def fact(self, id: Id) -> str:
        assert self.incident is not None
        return next(fact.what for fact in self.incident.facts if fact.id == id)

    def salvage_back(self) -> datetime:
        """When everything they've picked up of the salvage lies there again."""
        taken = [
            when
            for id, when in self.player.player.taken.items()
            if self.pickup(id).kind is PickupKind.SALVAGE
        ]
        return max(taken) + timedelta(hours=PLAYER_CONFIG.respawn)

    def morning(self) -> datetime:
        now = self.player.world.clock.now
        return (now + timedelta(days=1)).replace(hour=MORNING, minute=0, second=0, microsecond=0)


async def play(*, seed: int = 0, start: datetime = START, saves: Path | None = None) -> Result:
    """Plays the loop in a new village; with `saves`, writes each browser beat's world there."""
    from simile.app import create_app
    from simile.behaviour.mind import create_behaviour
    from simile.conversation import create_engine
    from simile.memory import MemoryStore
    from simile.story.begin import begin

    if saves is not None:
        saves.mkdir(parents=True, exist_ok=True)
        (saves / WORLD).unlink(missing_ok=True)
    world = World(Clock(start), FakeWallClock())
    app = create_app()
    app.state.world, app.state.headless = world, True
    app.state.memory = MemoryStore(saves / WORLD if saves else ":memory:")
    app.state.behaviour = create_behaviour(app, seed=seed)
    app.state.conversation = create_engine(app, seed=seed)
    await begin(app, rng=random.Random(f"story/{seed}"))
    async with app.router.lifespan_context(app):
        covers = Covers(alibis(investigation_of(app).incident))
        app.state.llm = LLMClient(covers)
        app.state.players.rng.seed(seed)
        result = await Playthrough(app, covers, Saves(app, saves)).run()
    return result


def report(result: Result) -> str:
    minutes = result.played / timedelta(minutes=1)
    lines = [
        *result.notes,
        "",
        f"{result.days:.2f} sim days: {minutes:.0f} minutes of play, and the rest waiting for "
        "salvage to lie there again.",
        f"Money by kind: {', '.join(f'{k} {v:g}' for k, v in sorted(result.earned.items()))}",
        f"Body: {', '.join(f'{part} {state}' for part, state in result.player.body)}",
        f"{result.attacker} lied, and flushed: {result.lie.line.text!r}",
        f"{result.refused_by} turned the player down.",
        f"Saw their bionics: {', '.join(sorted(result.seen_by))}",
        "Journal:",
        *(
            f"  {e.fact_id} from {e.source.name}"
            + ("" if e.flushed is None else f", flushed {e.flushed}")
            for e in result.journal
        ),
    ]
    return "\n".join(lines) + "\n"
