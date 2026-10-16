"""Rehearse the demo's opening without Claude: run its first sim minutes headless on the fake LLM
a number of times for each way the player might start, and count how often each scripted beat
happens.

    cd server && uv run python ../demo/check.py --runs 20
"""

import argparse
import asyncio
import json
import logging
import math
import os
import random
import statistics
import tempfile
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path

from prepare import HERE, prepare
from serve import keep_to_script, without_director
from starlette.applications import Starlette

from simile.app import create_app
from simile.behaviour.events import GoalChosen
from simile.protocol import PlayerMoveMessage, Position, hub_of
from simile.sim import Clock, ConversationStarted, FakeWallClock, World, world_of
from simile.world import movement_of
from simile.world.paths import Cell, find_path

BEATS = {
    "tobias seeks out kofi": ("goal", ("tobias", "seek", "kofi")),
    "tobias and kofi talk": ("talk", frozenset({"tobias", "kofi"})),
    "desmond seeks out marguerite": ("goal", ("desmond", "seek", "marguerite")),
    "desmond and marguerite talk": ("talk", frozenset({"desmond", "marguerite"})),
    "raymond goes to read at terminal_2": ("goal", ("raymond", "news", "terminal_2")),
}

WALKS: dict[str, tuple[str, ...]] = {
    "steps left and waits": (),
    "walks up to tobias or kofi": ("tobias", "kofi"),
    "walks up to desmond or marguerite": ("desmond", "marguerite"),
}
"""How the player starts: who they walk up to, if anyone, after their first step."""

PLAYER_SPEED = 2.6
"""Tiles per second, the client's `PLAYER_SPEED`."""
LEAVES_WITHIN = 2.0
"""The player sets off within this many sim seconds, to arrive around the scripted pairs' first
decisions."""


class Player:
    """A connected client whose player takes a step left from the square's entry, then maybe
    walks up to one of `towards`, sending a `player_move` from wherever they get to each tick."""

    def __init__(self, app: Starlette, towards: tuple[str, ...], rng: random.Random) -> None:
        self.hub, self.clock, self.movement = hub_of(app), world_of(app).clock, movement_of(app)
        self.towards, self.rng = towards, rng
        self.leaves = self.clock.now + timedelta(seconds=rng.uniform(0, LEAVES_WITHIN))
        spawn = self.movement.town.location("square").entry
        self.position: tuple[float, float] = (spawn.x, spawn.y)
        self.path = deque([(spawn.x - 1, spawn.y)])
        self.hub.connections.add(self)
        self._send()

    def put(self, frame: object) -> None:
        pass

    def tick(self, dt: float) -> None:
        if self.towards and not self.path and self.clock.now >= self.leaves:
            self.path = deque(self._route(self.rng.choice(self.towards)))
            self.towards = ()
        budget = PLAYER_SPEED * dt
        while self.path and budget > 0:
            gap = math.dist(self.position, self.path[0])
            step = min(budget, gap)
            budget -= step
            if step == gap:
                self.position = self.path.popleft()
            else:
                (x0, y0), (x1, y1) = self.position, self.path[0]
                self.position = (x0 + (x1 - x0) * step / gap, y0 + (y1 - y0) * step / gap)
        if budget < PLAYER_SPEED * dt:
            self._send()

    def _route(self, npc: str) -> list[Cell]:
        town, there = self.movement.town, self.movement.position(npc)
        taken = {(round(p.x), round(p.y)) for p in self.movement.entities().values()}
        beside = [
            cell
            for dx in (-1, 0, 1)
            for dy in (-1, 0, 1)
            if town.walkable(*(cell := (round(there.x) + dx, round(there.y) + dy)))
            and cell not in taken
        ]
        here = (round(self.position[0]), round(self.position[1]))
        path = find_path(town, here, self.rng.choice(beside)) if beside else None
        return (path or [])[1:]

    def _send(self) -> None:
        x, y = self.position
        self.hub.receive(PlayerMoveMessage(position=Position(x=x, y=y)).model_dump_json())


async def opening(
    minutes: float, towards: tuple[str, ...], rng: random.Random
) -> dict[tuple[str, object], datetime]:
    """When each goal was first chosen and each conversation first started."""
    world = World(Clock(), FakeWallClock())
    seen: dict[tuple[str, object], datetime] = {}
    world.bus.subscribe(
        GoalChosen,
        lambda event: seen.setdefault(
            ("goal", (event.npc, event.activity, event.target)), world.clock.now
        ),
    )
    world.bus.subscribe(
        ConversationStarted,
        lambda event: seen.setdefault(
            ("talk", frozenset(event.conversation.participants)), world.clock.now
        ),
    )
    app = create_app()
    app.state.world, app.state.headless = world, True
    async with app.router.lifespan_context(app):
        keep_to_script(app)
        without_director(app)
        world.loop.register(Player(app, towards, rng))
        await world.loop.run(timedelta(minutes=minutes))
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description="Rehearse the demo's opening on the fake LLM.")
    parser.add_argument("--runs", type=int, default=10, help="Runs for each way the player starts.")
    parser.add_argument("--minutes", type=float, default=2.0, help="Sim minutes per run.")
    args = parser.parse_args()
    os.environ["SIMILE_LLM"] = "fake"
    for name in ("SIMILE_FRESH", "SIMILE_NEWS", "SIMILE_NEWS_FEED", "SIMILE_RECORD"):
        os.environ.pop(name, None)
    logging.basicConfig(level=logging.ERROR)
    start = datetime.fromisoformat(json.loads((HERE / "scenario.json").read_text())["now"])
    rng = random.Random()
    missed = False
    with tempfile.TemporaryDirectory() as scratch:
        for walk, towards in WALKS.items():
            after: dict[str, list[float]] = {beat: [] for beat in BEATS}
            for run in range(args.runs):
                db = Path(scratch) / f"run-{run}.db"
                prepare(db)
                os.environ["SIMILE_DB"] = str(db)
                seen = asyncio.run(opening(args.minutes, towards, rng))
                for beat, wanted in BEATS.items():
                    if wanted in seen:
                        after[beat].append((seen[wanted] - start).total_seconds())
            print(f"The player {walk}:")
            for beat, times in after.items():
                when = f"after {statistics.median(times):.0f} sim seconds" if times else ""
                print(f"  {len(times):3} of {args.runs}  {beat:36} {when}")
            missed = missed or any(len(times) < args.runs for times in after.values())
    if missed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
