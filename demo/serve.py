"""`simile serve` for the demo, with the village held still until the player takes their first
step, so the opening plays to someone listening.

    cd server && uv run --extra voice python ../demo/serve.py --port 8000
"""

import argparse
import asyncio
import time

import uvicorn

from simile.app import create_app
from simile.protocol import PlayerMoveMessage, hub_of
from simile.sim import World


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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the demo village's sim server.")
    parser.add_argument("--port", type=int, default=8000)
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
            wall.release()
            print("The player has taken a step, so the village starts.", flush=True)

    hub_of(app).subscribe(PlayerMoveMessage, on_move)
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
