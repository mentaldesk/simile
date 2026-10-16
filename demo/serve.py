"""`simile serve` for the demo, with the village held still until the player takes their first
step, so the opening plays to someone listening, and then kept to the opener's script, with
the ambient director off.

    cd server && uv run --extra voice python ../demo/serve.py --port 8000
"""

import argparse
import asyncio
import time
from datetime import timedelta

import uvicorn
from starlette.applications import Starlette

from simile.ambient import director_of
from simile.app import create_app
from simile.behaviour import behaviour_of
from simile.conversation import conversations_of
from simile.protocol import PlayerMoveMessage, hub_of
from simile.sim import ConversationStarted, World, world_of

SCRIPTED = (frozenset({"tobias", "kofi"}), frozenset({"desmond", "marguerite"}))
SCRIPT_CAP = timedelta(minutes=2)


class HeldWallClock:
    """Real time that stands still until `release`, so the tick loop's first tick waits for it."""

    def __init__(self) -> None:
        self.released = asyncio.Event()
        self._start = time.monotonic()
        self._held = 0.0

    def now(self) -> float:
        return time.monotonic() - self._held if self.released.is_set() else self._start

    async def sleep(self, seconds: float) -> None:
        await self.released.wait()
        await asyncio.sleep(seconds)

    def release(self) -> None:
        if not self.released.is_set():
            self._held = time.monotonic() - self._start
            self.released.set()


class ScriptHold:
    """Neither of a scripted pair seeks out or greets the player until one of them starts talking,
    which on script is to the other. Until both pairs have, nobody's choices are left to chance.
    After `cap` of sim time it lets go regardless, so a pair that never talks doesn't ignore the
    player all session."""

    def __init__(self, app: Starlette, cap: timedelta = SCRIPT_CAP) -> None:
        world = world_of(app)
        self.clock = world.clock
        self.behaviour, self.engine = behaviour_of(app), conversations_of(app)
        self.usual = self.behaviour.config, self.engine.config
        self.behaviour.config = self.behaviour.config.model_copy(update={"temperature": 0.0})
        self.engine.config = self.engine.config.model_copy(update={"accept_temperature": 0.0})
        self.behaviour.leave_player_alone.update(*SCRIPTED)
        self.waiting = set(SCRIPTED)
        self.until = self.clock.now + cap
        self._unsubscribe = world.bus.subscribe(ConversationStarted, self.started)
        self._unregister = world.loop.register(self)

    def started(self, event: ConversationStarted) -> None:
        talking = set(event.conversation.participants)
        self._let_go([pair for pair in self.waiting if pair & talking])

    def tick(self, dt: float) -> None:
        if self.clock.now >= self.until:
            self._let_go(list(self.waiting))

    def _let_go(self, pairs: list[frozenset[str]]) -> None:
        for pair in pairs:
            self.waiting.remove(pair)
            self.behaviour.leave_player_alone.difference_update(pair)
        if not self.waiting:
            self.behaviour.config, self.engine.config = self.usual
            self._unsubscribe()
            self._unregister()


def without_director(app: Starlette) -> None:
    """The ambient director nudges nobody, so the walk-through's later beats stay put."""
    director = director_of(app)
    director.config = director.config.model_copy(update={"enabled": False})


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the demo village's sim server.")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument(
        "--script-cap",
        type=float,
        default=SCRIPT_CAP.total_seconds(),
        help="Sim seconds from the first step before the scripted pairs are let go regardless.",
    )
    args = parser.parse_args()

    wall = HeldWallClock()
    app = create_app()
    app.state.world = World(wall=wall)
    first: list[tuple[float, float]] = []

    def on_move(message: PlayerMoveMessage) -> None:
        here = (message.position.x, message.position.y)
        if not first:
            first.append(here)
        elif here != first[0] and not wall.released.is_set():
            ScriptHold(app, timedelta(seconds=args.script_cap))
            without_director(app)
            wall.release()
            print("The player has taken a step, so the village starts.", flush=True)

    hub_of(app).subscribe(PlayerMoveMessage, on_move)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
