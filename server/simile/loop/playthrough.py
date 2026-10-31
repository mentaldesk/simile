import json
import math
import random
import sqlite3
import sys
from collections.abc import AsyncGenerator, Collection
from contextlib import closing
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from pathlib import Path

from starlette.applications import Starlette

from simile.conversation.prompt import CUES, Cue
from simile.economy import PLAYER, Kind
from simile.llm import LLMClient
from simile.llm.fake import FakeProvider
from simile.llm.lifespan import CannedProvider
from simile.llm.provider import Request, Usage
from simile.loop.player import LoopPlayer, Refused
from simile.persistence import investigation_of
from simile.player.config import DEFAULT_CONFIG as PLAYER_CONFIG
from simile.reflection.extraction import SYSTEM as REFLECTING
from simile.schema import (
    PLAYER_ID,
    Bionic,
    BodyPart,
    CreatureKind,
    Id,
    ItemKind,
    JournalEntry,
    MemoryKind,
    Player,
)
from simile.sim import Clock, FakeWallClock, World
from simile.social.bionics import TOPIC as BIONICS
from simile.social.bionics import tolerance
from simile.social.config import DEFAULT_BIONICS
from simile.story import NOTES, load_story
from simile.story.content import HATCH, TERMINAL
from simile.story.disappearance import HATCH_LOG, LIFT_LOG, NOTED
from simile.street.jump import JUMP
from simile.street.sewers import GATE_BOX, SEWERS
from simile.world.map import Pickup, PickupKind
from simile.world.paths import Spot

START = datetime(2026, 10, 19, 8, tzinfo=UTC)
WORLD = "world.db"
SQUARE = "square"
OUTSIDE_THE_CLINIC = Spot("metro", 87, 15)
"""Two cells short of the clinic's door, where the browser's beats at the clinic start."""
LIFT = Spot("metro", 100, 15)
LANDING = Spot(SEWERS, 2, 15)
DAYS = 7
"""The most days of salvage rounds a bionic may wait for."""
HELLO = "Hello there! Lovely day for it."
REFUSAL = CUES[Cue.REFUSE].split("{other}")[0]
METRO = (
    "metro_ticket_machine",
    "metro_fridge",
    "metro_freight_crates",
    "metro_container",
    "metro_switchboard",
    "metro_relay_rack",
    "metro_tool_crate",
    "metro_lockers",
)
"""The metro's finds on their own legs: the cell's and datajack's parts, spares, a ration pack."""
LEGS = ("sewers_bedroll_legs", "sewers_crates_legs")
FEET = ("sewers_bedroll_feet", "sewers_crates_feet")
CAVE = "sewers_secret_cave"
"""Past the bats, which the infrared eye is for."""


class Canned:
    """The canned fake LLM, with nothing to reflect on, noting each prompt to turn them down."""

    name = "canned"

    def __init__(self) -> None:
        self.canned = CannedProvider()
        self.refusals: list[str] = []
        """Each prompt that cued a resident to turn the player down."""

    def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        prompt = "\n".join(message.content for message in request.messages)
        if REFUSAL in prompt:
            self.refusals.append(prompt)
        if request.system.startswith(REFLECTING):
            return FakeProvider(['{"reflections": []}']).stream(request)
        return self.canned.stream(request)


class Saves:
    """The world before each browser beat: its database, and where the beat starts, in JSON."""

    def __init__(self, app: Starlette, folder: Path | None) -> None:
        self.app = app
        self.folder = folder

    async def write(self, beat: str, player: LoopPlayer, **extra: object) -> None:
        if self.folder is None:
            return
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
    refused_by: Id
    seen_by: dict[Id, list[str]]
    hurt: list[str]
    dark: list[str]
    stomped: int
    leapt: int
    lamp_off_by_bats: int
    roused: set[Id]
    earned: dict[Kind, float] = field(default_factory=dict)
    """The player's money in and out of the ledger by kind: out is negative."""

    @property
    def days(self) -> float:
        return (self.end - self.start) / timedelta(days=1)

    @property
    def played(self) -> timedelta:
        return self.end - self.start - self.away


class Playthrough:
    """Stage 2's loop, played in order."""

    def __init__(self, app: Starlette, canned: Canned, saves: Saves) -> None:
        self.app, self.canned, self.saves = app, canned, saves
        self.notes: list[str] = []
        self.player = LoopPlayer(app, self.notes)
        self.disappearance = investigation_of(app).disappearance
        assert self.disappearance is not None

    def pickup(self, id: Id) -> Pickup:
        towns = self.player.movement.maps.values()
        return next(pickup for town in towns for pickup in town.pickups if pickup.id == id)

    def stand(self, id: Id) -> Spot:
        thing = self.player.thing(id)
        return Spot(thing.map, thing.stand[0].x, thing.stand[0].y)

    async def run(self) -> Result:
        start = self.player.world.clock.now
        await self.sell_a_kidney()
        await self.the_power_cell()
        await self.the_datajack()
        await self.the_rats()
        await self.the_legs()
        await self.the_gate()
        await self.the_feet()
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
            refused_by,
            seen_by,
            p.hurt,
            p.dark,
            p.stomped,
            p.leapt,
            p.lamp_off_by_bats,
            p.roused,
            earned,
        )

    async def sell_a_kidney(self) -> None:
        """The doctor tells them the power cell's recipe as they walk in, and buys a kidney."""
        p = self.player
        p.join(p.entry(SQUARE))
        await p.go(OUTSIDE_THE_CLINIC)
        await self.saves.write("kidney", p)
        await p.clinic()
        await p.wait(1)
        if Bionic.POWER_CELL not in p.player.mind.recipes:
            raise Refused("The doctor didn't tell them the power cell's recipe")
        p.note("The doctor told them the power cell's recipe")
        await p.sell_part("left_kidney")

    async def the_power_cell(self) -> None:
        """The maker space's finds, then the metro's while its bots ignore a whole player."""
        p = self.player
        for id in ("maker_space_bench", "maker_space_spares", "maker_space_shelf"):
            await p.search(id)
        await self.gather({"metro"}, finds=METRO)
        await self.fitted(Bionic.POWER_CELL, "stomach", "cell")

    async def the_datajack(self) -> None:
        p = self.player
        await p.to(LIFT)
        if p.kept(LANDING):
            raise Refused("The server let the player into the sewers without the datajack")
        p.note("The lift didn't take them without the datajack")
        await self.fitted(Bionic.DATAJACK, "vertebra", "datajack", lift_log=self.fact(LIFT_LOG))
        if LIFT_LOG not in await p.find(self.stand(TERMINAL)):
            raise Refused("The dead terminal held no clue")
        await p.to(LANDING)

    async def the_rats(self) -> None:
        """Stomps the biggest nest's rats as they come for the ration pack."""
        p = self.player
        if not p.carries(ItemKind.FOOD):
            raise Refused("They have no food to draw the rats")
        rats = [c for c in p.creatures.values() if c.kind is CreatureKind.RAT]
        rows: dict[tuple[str, int], list[float]] = {}
        for rat in rats:
            rows.setdefault((rat.position.map, round(rat.position.y)), []).append(rat.position.x)
        (map, row), xs = max(rows.items(), key=lambda kv: len(kv[1]))
        town, middle = p.movement.maps[map], round(sum(xs) / len(xs))
        floor = {middle}
        for side in (-1, 1):
            x = middle + side
            while town.standing(x, row):
                floor.add(x)
                x += side
        stand = min(
            (x for x in floor if abs(x - middle) >= 3 and not town.climb(x, row - 1)),
            key=lambda x: abs(x - middle),
        )
        stomped = p.stomped
        await p.to(Spot(map, stand, row))
        for _ in range(300):
            await p.dodge(p.at)
            await p.wait(0.1)
            if p.stomped - stomped >= len(xs):
                break
        if p.stomped == stomped:
            raise Refused("No rat came for the food")

    async def the_legs(self) -> None:
        """Zone 0's delver's bedroll and crates, with the lamp off by the bats."""
        p = self.player
        for id in LEGS:
            await p.search(id)
        await self.gather({SEWERS}, enough=self.price(Bionic.BIONIC_LEGS))
        await self.fitted(Bionic.BIONIC_LEGS, "legs", "legs")

    async def the_gate(self) -> None:
        """Over the gate's gap on the legs, and on to the hatch."""
        p, box = self.player, self.stand(GATE_BOX)
        hatch = self.stand(HATCH)
        if hatch in p.reach(JUMP):
            raise Refused("The hatch is in reach on the player's own legs")
        await p.to(box)
        route = p.route(hatch)
        assert route is not None
        a, b = next((a, b) for a, b in pairwise(route) if a.map == b.map and abs(b.x - a.x) >= 5)
        await p.go(a)
        await self.saves.write("gate", p, gap={"from": a.x, "to": b.x, "row": a.y})
        await p.go(b)
        p.note(f"Jumped the gate's gap from {a.x} to {b.x}")
        await p.to(p.beside(hatch, (2, 3)))
        await self.saves.write("hatch", p, hatch_log=self.fact(HATCH_LOG))
        if HATCH_LOG not in await p.find(hatch):
            raise Refused("The hatch held no clue")

    async def the_feet(self) -> None:
        """Zone 1's bedroll and crates, the feet, and the metro's high ledge with them."""
        p, ledge = self.player, self.pickup("metro_secret_ledge")
        if Spot(ledge.map, ledge.x, ledge.y) in p.reach():
            raise Refused("The high ledge is in reach without the feet")
        for id in FEET:
            await p.search(id)
        await self.gather({SEWERS}, enough=self.price(Bionic.SPRING_FEET), skip={CAVE})
        await self.fitted(Bionic.SPRING_FEET, "feet", "feet")
        await p.take(ledge)

    async def fitted(self, bionic: Bionic, part: BodyPart, beat: str, **extra: object) -> None:
        """Pays for `bionic` a day at a time and is fitted with it, saving the beat first."""
        p, price = self.player, self.price(bionic)
        for _ in range(DAYS):
            if p.money < price:
                await p.clinic()
                await p.sell_recipes()
            if p.money < price:
                await self.gather({"metro", SEWERS}, enough=price, skip={CAVE})
            if p.money >= price:
                break
            await p.come_back(self.salvage_back())
        else:
            raise Refused(f"{DAYS} days of salvage didn't pay for {bionic}")
        if p.spare():
            await p.sell()
        await p.to(OUTSIDE_THE_CLINIC)
        await self.saves.write(beat, p, **extra)
        await p.clinic()
        await p.fit(bionic, part)

    def price(self, bionic: Bionic) -> float:
        return next(r.credits for r in self.player.state.recipes if r.bionic is bionic)

    async def gather(
        self,
        maps: Collection[str],
        enough: float = math.inf,
        finds: Collection[Id] = (),
        skip: Collection[Id] = (),
    ) -> None:
        """Searches `finds` and picks up what pays on `maps`, nearest first, selling when full."""
        p = self.player
        while p.money < enough:
            await p.fed()
            things = [
                (p.away_from(stand.x, stand.map), id)
                for id in finds
                if id not in p.player.searched
                and (stand := self.stand(id)) in p.reach()
                and p.fits(p.thing(id).items)
            ]
            near = [
                (p.away_from(pickup.x, pickup.map), pickup.id)
                for pickup, pile in p.lying(maps)
                if pickup.id not in skip
                and (pile.money or any(item.kind is ItemKind.SALVAGE for item in pile.items))
                and Spot(pickup.map, pickup.x, pickup.y) in p.reach()
                and p.fits(pile.items)
            ]
            if things or near:
                _, id = min([*things, *near])
                if id in finds:
                    await p.search(id)
                else:
                    await p.take(self.pickup(id))
            elif p.spare():
                await p.sell()
            else:
                return

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
            refusals = len(self.canned.refusals)
            _, ended = await p.say(npc, HELLO)
            if ended and len(self.canned.refusals) > refusals:
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

    def fact(self, id: Id) -> str:
        assert self.disappearance is not None
        return next(fact.what for fact in self.disappearance.facts if fact.id == id)

    def salvage_back(self) -> datetime:
        """When everything they've picked up of the salvage lies there again."""
        taken = [
            when
            for id, when in self.player.player.taken.items()
            if self.pickup(id).kind is PickupKind.SALVAGE
        ]
        return max(taken) + timedelta(hours=PLAYER_CONFIG.respawn)


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
        canned = Canned()
        app.state.llm = LLMClient(canned)
        app.state.players.rng.seed(seed)
        result = await Playthrough(app, canned, Saves(app, saves)).run()
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
        f"Came down on {result.stomped} rats, jumped {result.leapt} bots and kept the lamp off by "
        f"the bats {result.lamp_off_by_bats} times.",
        f"Hurt {len(result.hurt)} times; the lamp ran flat in the dark {len(result.dark)} times; "
        f"{len(result.roused)} bats came for them.",
        *result.hurt,
        *result.dark,
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
