import math
import time
from collections import Counter, defaultdict
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from starlette.applications import Starlette

from simile.behaviour.config import Activity
from simile.behaviour.events import GoalChosen
from simile.behaviour.mind import (
    Behaviour,
    create_behaviour,
    decline,
    no_conversations,
    skip_news,
)
from simile.schema import CoreValue, Id, LocationKind
from simile.sim import Clock, FakeWallClock, World

HOME = "home"
STREET = "street"
TERMINAL = "terminal"
PLACES = (HOME, STREET, "coffee_shop", "square", TERMINAL, "park", "noodle_bar", "maker_space")
NIGHT = (1.0, 5.0)
NEWS_INTEREST = 0.6


@dataclass
class Observer:
    """Where every NPC is, once a sim minute, and the goals they choose."""

    behaviour: Behaviour
    every: timedelta = timedelta(minutes=1)
    by_hour: dict[int, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    samples: Counter[int] = field(default_factory=Counter)
    out: Counter[Id] = field(default_factory=Counter)
    near: Counter[Id] = field(default_factory=Counter)
    out_at_night: Counter[datetime] = field(default_factory=Counter)
    goals: dict[Id, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))

    def __post_init__(self) -> None:
        self.next = self.behaviour.clock.now

    def on_goal(self, event: GoalChosen) -> None:
        self.goals[event.npc][event.activity] += 1

    def tick(self, dt: float) -> None:
        clock = self.behaviour.clock
        if clock.now < self.next:
            return
        self.next += self.every
        hour = clock.time_of_day
        positions = self.behaviour.movement.entities()
        self.samples[int(hour)] += 1
        for npc in self.behaviour.npcs.values():
            place = self.place(npc.id, npc.home)
            self.by_hour[int(hour)][place] += 1
            if place == HOME:
                continue
            self.out[npc.id] += 1
            if NIGHT[0] <= hour < NIGHT[1]:
                self.out_at_night[clock.now] += 1
            here = positions[npc.id]
            if any(
                math.dist(here, positions[other]) <= self.behaviour.config.near
                for other in self.behaviour.npcs
                if other != npc.id
            ):
                self.near[npc.id] += 1

    def place(self, npc: Id, home: Id) -> str:
        location = self.behaviour.places.at(self.behaviour.movement.position(npc))
        if location is None:
            return STREET
        if location.kind is LocationKind.HOUSE:
            return HOME if location.id == home else STREET
        if location.kind is LocationKind.TERMINAL:
            return TERMINAL
        return location.id


async def simulate(hours: float, *, start: datetime, seed: int = 0) -> tuple[Observer, float]:
    """Run memory, world and behaviour for `hours` of sim time as fast as the CPU allows.
    Conversations and news stay stubbed, so nothing calls Claude: there's always an article of
    `NEWS_INTEREST` to read, and reading it does nothing."""
    from simile.behaviour.lifespan import lifespan as behaviour
    from simile.memory.lifespan import lifespan as memory
    from simile.world.lifespan import lifespan as world_lifespan

    app = Starlette()
    world = World(Clock(start), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.behaviour = create_behaviour(app, seed=seed)
    observer = Observer(app.state.behaviour)
    world.bus.subscribe(GoalChosen, observer.on_goal)
    started = time.perf_counter()
    async with AsyncExitStack() as stack:
        for hook in (behaviour, memory, world_lifespan):
            await stack.enter_async_context(hook(app))
        app.state.behaviour.hooks.set(
            request_conversation=decline,
            read_news=skip_news,
            news_interest=lambda npc: NEWS_INTEREST,
            conversations=no_conversations,
        )
        world.loop.register(observer)
        await world.loop.run(timedelta(hours=hours))
    return observer, time.perf_counter() - started


def ranks(values: list[float]) -> list[float]:
    order = sorted(range(len(values)), key=values.__getitem__)
    result = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for k in range(i, j + 1):
            result[order[k]] = (i + j) / 2
        i = j + 1
    return result


def spearman(xs: list[float], ys: list[float]) -> float:
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    cov = sum((a - mx) * (b - my) for a, b in zip(rx, ry, strict=True))
    spread = math.sqrt(sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry))
    return cov / spread if spread else 0.0


def report(observer: Observer, hours: float, start: datetime, seed: int, seconds: float) -> str:
    behaviour = observer.behaviour
    npcs = sorted(behaviour.npcs.values(), key=lambda npc: npc.values[CoreValue.CONNECTION])
    connection = [npc.values[CoreValue.CONNECTION] for npc in npcs]
    near = [observer.near[npc.id] for npc in npcs]
    lines = [
        f"Simulated {hours:g} sim hours from {start:%Y-%m-%d %H:%M} UTC, seed {seed}, "
        f"in {seconds:.0f} s.",
        "",
        "**Time near others by Connection.** Minutes out of home, and of those, minutes within "
        f"{behaviour.config.near:g} tiles of another NPC.",
        "",
        "| NPC | Connection | Out | Near others | Share |",
        "|---|--:|--:|--:|--:|",
    ]
    for npc, value, minutes in zip(npcs, connection, near, strict=True):
        out = observer.out[npc.id]
        share = f"{minutes / out:.0%}" if out else "-"
        lines.append(f"| {npc.id} | {value:.2f} | {out} | {minutes} | {share} |")
    lines += [
        "",
        f"Spearman rank correlation of Connection with minutes near others: "
        f"{spearman(connection, [float(m) for m in near]):.2f}.",
        "",
        "**Where people are by hour.** Average number of NPCs in each place.",
        "",
        "| Hour | " + " | ".join(PLACES) + " |",
        "|--:|" + "--:|" * len(PLACES),
    ]
    first = int(start.hour)
    for offset in range(24):
        hour = (first + offset) % 24
        if not observer.samples[hour]:
            continue
        counts = observer.by_hour[hour]
        cells = [_count(counts[place] / observer.samples[hour]) for place in PLACES]
        lines.append(f"| {hour:02d} | " + " | ".join(cells) + " |")
    night = observer.out_at_night
    at_three = sum(n for when, n in night.items() if (when.hour, when.minute) == (3, 0))
    lines += [
        "",
        f"**Night.** Out of home at 03:00: {at_three}. Most out at once between "
        f"{NIGHT[0]:02.0f}:00 and {NIGHT[1]:02.0f}:00: {max(night.values(), default=0)}.",
        "",
        "**Goals chosen.**",
        "",
        "| NPC | " + " | ".join(a.value for a in GOALS) + " |",
        "|---|" + "--:|" * len(GOALS),
    ]
    for npc in npcs:
        goals = observer.goals[npc.id]
        lines.append(f"| {npc.id} | " + " | ".join(str(goals[a]) for a in GOALS) + " |")
    return "\n".join(lines) + "\n"


GOALS = tuple(a for a in Activity if a is not Activity.TALK)


def _count(value: float) -> str:
    return f"{value:.1f}" if value else "·"
