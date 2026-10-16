"""Rehearse the demo's opening without Claude: run its first sim minutes headless on the fake LLM
a number of times and count how often each scripted beat happens.

    cd server && uv run python ../demo/check.py --runs 20
"""

import argparse
import asyncio
import json
import logging
import os
import statistics
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

from prepare import HERE, prepare

BEATS = {
    "tobias seeks out kofi": ("goal", ("tobias", "seek", "kofi")),
    "tobias and kofi talk": ("talk", frozenset({"tobias", "kofi"})),
    "desmond seeks out marguerite": ("goal", ("desmond", "seek", "marguerite")),
    "desmond and marguerite talk": ("talk", frozenset({"desmond", "marguerite"})),
    "raymond goes to read at terminal_2": ("goal", ("raymond", "news", "terminal_2")),
}


async def opening(minutes: float) -> dict[tuple[str, object], datetime]:
    """When each goal was first chosen and each conversation first started."""
    from simile.behaviour.events import GoalChosen
    from simile.sim import Clock, ConversationStarted, FakeWallClock, World
    from simile.sim.headless import run_headless

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
    await run_headless(world, timedelta(minutes=minutes))
    return seen


def main() -> None:
    parser = argparse.ArgumentParser(description="Rehearse the demo's opening on the fake LLM.")
    parser.add_argument("--runs", type=int, default=10)
    parser.add_argument("--minutes", type=float, default=2.0, help="Sim minutes per run.")
    args = parser.parse_args()
    os.environ["SIMILE_LLM"] = "fake"
    for name in ("SIMILE_FRESH", "SIMILE_NEWS", "SIMILE_NEWS_FEED", "SIMILE_RECORD"):
        os.environ.pop(name, None)
    logging.basicConfig(level=logging.ERROR)
    start = datetime.fromisoformat(json.loads((HERE / "scenario.json").read_text())["now"])
    after: dict[str, list[float]] = {beat: [] for beat in BEATS}
    with tempfile.TemporaryDirectory() as scratch:
        for run in range(args.runs):
            db = Path(scratch) / f"run-{run}.db"
            prepare(db)
            os.environ["SIMILE_DB"] = str(db)
            seen = asyncio.run(opening(args.minutes))
            for beat, wanted in BEATS.items():
                if wanted in seen:
                    after[beat].append((seen[wanted] - start).total_seconds())
    for beat, times in after.items():
        when = f"after {statistics.median(times):.0f} sim seconds" if times else ""
        print(f"{len(times):3} of {args.runs}  {beat:36} {when}")
    if any(len(times) < args.runs for times in after.values()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
