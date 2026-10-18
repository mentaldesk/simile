import math
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from starlette.applications import Starlette

from simile.behaviour.config import Activity, Need
from simile.behaviour.events import GoalChosen
from simile.behaviour.mind import (
    Behaviour,
    create_behaviour,
    no_conversations,
    skip_news,
)
from simile.behaviour.scoring import Goal, MuralSpot, Supply
from simile.schema import CoreValue, Id, LocationKind, Medium, Npc, Traits
from simile.sim import Clock, FakeWallClock, World

if TYPE_CHECKING:
    from simile.economy.economy import Economy

HOME = "home"
STREET = "street"
TERMINAL = "terminal"
PLACES = (
    HOME,
    STREET,
    "coffee_shop",
    "cafe_terrace",
    "square",
    TERMINAL,
    "park",
    "noodle_bar",
    "maker_space",
    "gallery",
)
NIGHT = (1.0, 5.0)
NEWS_INTEREST = 0.6
MEAL = 0.3
"""How far hunger falls in one go for it to count as a meal."""
AGAIN = timedelta(minutes=90)
"""As G1's `again`: someone served at the café this recently just sits down."""
MONEY_EVERY = timedelta(hours=12)


@dataclass(frozen=True)
class Meal:
    npc: Id
    at: datetime
    place: str
    hunger: float
    """How hungry they were when they started eating."""


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
    awake: Counter[Id] = field(default_factory=Counter)
    creating: Counter[Id] = field(default_factory=Counter)
    works: dict[Id, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    """Where each NPC made their works: home, a place, or for a mural its wall."""
    talk: float | None = None
    """Minutes each conversation lasts when every request to talk is accepted, or None to decline
    them all."""
    started: Counter[Id] = field(default_factory=Counter)
    ending: list[tuple[datetime, Id, Id]] = field(default_factory=list)
    awake_at: Counter[str] = field(default_factory=Counter)
    """Waking minutes in each place."""
    needs: dict[Need, list[tuple[float, bool]]] = field(default_factory=lambda: defaultdict(list))
    """Every resident's needs once a sim minute, and whether they were awake. Inspiration only
    for those with a craft."""
    meals: list[Meal] = field(default_factory=list)
    hunger: dict[Id, float] = field(default_factory=dict)
    eating: dict[Id, tuple[Meal, float]] = field(default_factory=dict)
    """Meals going on, with how hungry they were at the last sample."""
    economy: "Economy | None" = None
    open: Callable[[], bool] = lambda: False
    """Whether the Daily Grind is serving."""
    served: dict[Id, datetime] = field(default_factory=dict)
    visits: dict[Id, datetime] = field(default_factory=dict)
    money: dict[Id, list[float]] = field(default_factory=lambda: defaultdict(list))
    """Each resident's money every `MONEY_EVERY`, from the start."""
    least: dict[Id, float] = field(default_factory=dict)
    stays: Counter[str] = field(default_factory=Counter)
    """Minutes staying in each place out of home: there, awake and not walking."""
    on_spot: Counter[str] = field(default_factory=Counter)
    """Of those, minutes on a spot."""

    def __post_init__(self) -> None:
        self.next = self.behaviour.clock.now
        self.next_money = self.next

    def request_conversation(self, a: Id, b: Id) -> bool:
        if self.talk is None:
            return False
        self.started[a] += 1
        self.ending.append((self.behaviour.clock.now + timedelta(minutes=self.talk), a, b))
        return True

    def on_goal(self, event: GoalChosen) -> None:
        self.goals[event.npc][event.activity] += 1

    def on_create(self, npc: Npc, wall: Id | None) -> None:
        target = self.behaviour.goal(npc.id).target
        self.works[npc.id][wall or (HOME if target == npc.home else str(target))] += 1

    def mural_wall(self, npc: Npc) -> MuralSpot | None:
        """The map's walls in turn, moving on to the next after each mural."""
        walls = self.behaviour.movement.town.murals
        if not walls:
            return None
        muralists = sorted(n.id for n in self.behaviour.npcs.values() if _medium(n) is Medium.MURAL)
        wall = walls[(muralists.index(npc.id) + sum(self.works[npc.id].values())) % len(walls)]
        return MuralSpot(wall.id, wall.stand)

    def tick(self, dt: float) -> None:
        clock = self.behaviour.clock
        for over in [talk for talk in self.ending if talk[0] <= clock.now]:
            self.ending.remove(over)
            for npc in over[1:]:
                self.behaviour.resume(npc)
        if clock.now < self.next:
            return
        self.next += self.every
        self.serve(clock.now)
        self.sample_money(clock.now)
        hour = clock.time_of_day
        positions = self.behaviour.movement.entities()
        self.samples[int(hour)] += 1
        for npc in self.behaviour.npcs.values():
            place = self.place(npc.id, npc.home)
            self.by_hour[int(hour)][place] += 1
            mind = self.behaviour.minds[npc.id]
            self.sample_needs(npc, place)
            if mind.goal.activity is not Activity.SLEEP:
                self.awake[npc.id] += 1
                self.awake_at[place] += 1
            if mind.goal.activity is Activity.CREATE and mind.walk is None:
                self.creating[npc.id] += 1
            if (
                place not in (HOME, STREET)
                and mind.walk is None
                and mind.goal.activity is not Activity.SLEEP
            ):
                self.stays[place] += 1
                self.on_spot[place] += self.behaviour.movement.on_spot(npc.id) is not None
            if place == HOME:
                continue
            self.out[npc.id] += 1
            if NIGHT[0] <= hour < NIGHT[1]:
                self.out_at_night[clock.now] += 1
            here = positions[npc.id]
            if any(
                (there := positions[other]).map == here.map
                and math.dist(here, there) <= self.behaviour.config.near
                for other in self.behaviour.npcs
                if other != npc.id
            ):
                self.near[npc.id] += 1

    def serve(self, now: datetime) -> None:
        """G1's orders without the café: whoever arrives at the Daily Grind while it's serving,
        unless they were served there lately, is served a drink."""
        from simile.cafe.cafe import barista
        from simile.cafe.config import DEFAULT_CONFIG as CAFE
        from simile.cafe.events import Served

        behaviour = self.behaviour
        server = barista(behaviour.npcs.values(), CAFE.home)
        if server is None or not self.open():
            return
        for npc, mind in behaviour.minds.items():
            arrived = mind.goal == Goal(Activity.COFFEE_SHOP, CAFE.home) and mind.walk is None
            if npc == server or not arrived or self.visits.get(npc) == mind.since:
                continue
            self.visits[npc] = mind.since
            if (last := self.served.get(npc)) is None or now - last >= AGAIN:
                self.served[npc] = now
                behaviour.bus.publish(Served(npc, server, "coffee", 0.0, False))

    def sample_money(self, now: datetime) -> None:
        if self.economy is None:
            return
        for npc, amount in self.economy.money.items():
            self.least[npc] = min(self.least.get(npc, amount), amount)
        if now >= self.next_money:
            self.next_money += MONEY_EVERY
            for npc, amount in self.economy.money.items():
                self.money[npc].append(amount)

    def sample_needs(self, npc: Npc, place: str) -> None:
        mind = self.behaviour.minds[npc.id]
        awake = mind.goal.activity is not Activity.SLEEP
        for need, value in mind.needs.items():
            if npc.craft or need is not Need.INSPIRATION:
                self.needs[need].append((value, awake))
        hunger, before = mind.needs[Need.HUNGER], self.hunger.get(npc.id, 0.0)
        self.hunger[npc.id] = hunger
        meal = self.eating.pop(npc.id, None)
        if mind.eating.get(Need.HUNGER) == mind.since:
            start = meal[0] if meal else Meal(npc.id, self.behaviour.clock.now, place, before)
            self.eating[npc.id] = (start, hunger)
        elif meal is not None and meal[0].hunger - meal[1] >= MEAL:
            self.meals.append(meal[0])

    def place(self, npc: Id, home: Id) -> str:
        location = self.behaviour.places.at(self.behaviour.movement.position(npc))
        if location is None:
            return STREET
        if location.id == home:
            return HOME
        if location.kind is LocationKind.HOUSE:
            return STREET
        if location.kind is LocationKind.TERMINAL:
            return TERMINAL
        return location.id


async def simulate(
    hours: float,
    *,
    start: datetime,
    seed: int = 0,
    npcs: Iterable[Npc] | None = None,
    traits: Mapping[Id, Traits] | None = None,
    talk: float | None = None,
) -> tuple[Observer, float]:
    """Run memory, world, behaviour and E3's economy for `hours` of sim time as fast as the CPU
    allows, with N1's NPCs and the cast's traits unless given others. The Daily Grind serves
    whoever arrives while it's open, as G1 would. Conversations, news and works stay
    stubbed, so nothing calls Claude: every request to talk is declined, or with `talk` accepted
    and over after that many minutes, there's always an article of `NEWS_INTEREST` to read,
    muralists paint the map's walls in turn, and reading or making something does nothing."""
    from simile.behaviour.lifespan import lifespan as behaviour
    from simile.economy.economy import economy_of
    from simile.economy.lifespan import lifespan as economy
    from simile.memory.lifespan import lifespan as memory
    from simile.world.lifespan import lifespan as world_lifespan

    app = Starlette()
    world = World(Clock(start), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.behaviour = create_behaviour(app, seed=seed, npcs=npcs, traits=traits)
    supply, opened = daily_grind(app.state.behaviour)
    observer = Observer(app.state.behaviour, talk=talk, economy=economy_of(app), open=opened)
    world.bus.subscribe(GoalChosen, observer.on_goal)
    started = time.perf_counter()
    async with AsyncExitStack() as stack:
        for hook in (behaviour, economy, memory, world_lifespan):
            await stack.enter_async_context(hook(app))
        app.state.behaviour.hooks.set(
            request_conversation=observer.request_conversation,
            read_news=skip_news,
            news_interest=lambda npc: NEWS_INTEREST,
            conversations=no_conversations,
            create=observer.on_create,
            mural_wall=observer.mural_wall,
            supply=supply,
        )
        world.loop.register(observer)
        await world.loop.run(timedelta(hours=hours))
    return observer, time.perf_counter() - started


def daily_grind(behaviour: Behaviour) -> tuple[Supply, Callable[[], bool]]:
    """G1's shifts without the café: the Daily Grind serves only while it has a barista and
    she's at work. Its supply hook, and whether it's serving."""
    from simile.cafe.cafe import barista
    from simile.cafe.config import DEFAULT_CONFIG as CAFE

    shop = Goal(Activity.COFFEE_SHOP, CAFE.home)
    staffed = barista(behaviour.npcs.values(), CAFE.home) is not None

    def serving() -> bool:
        return staffed and CAFE.opens <= behaviour.clock.time_of_day < CAFE.closes

    def supply(goal: Goal, need: Need) -> float:
        if goal != shop or need is not Need.HUNGER:
            return 1.0
        return float(serving())

    return supply, serving


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
    lines += ["", *shares(observer), "", *meals(observer, hours), "", *needs(observer)]
    lines += ["", *works(observer, hours)]
    lines += ["", *spots(observer)]
    if observer.talk is not None:
        lines += ["", *conversations(observer, hours)]
    if observer.economy is not None:
        lines += ["", *shifts(observer), "", *money(observer), "", *ledger(observer)]
    return "\n".join(lines) + "\n"


def conversations(observer: Observer, hours: float) -> list[str]:
    behaviour = observer.behaviour
    npcs = sorted(behaviour.npcs.values(), key=lambda npc: behaviour.traits_of(npc.id).sociability)
    sociability = [behaviour.traits_of(npc.id).sociability for npc in npcs]
    started = [observer.started[npc.id] for npc in npcs]
    lines = [
        f"**Conversations.** Every request to talk was accepted and lasted {observer.talk:g} "
        "minutes. How many each resident started, by sociability.",
        "",
        "| NPC | Sociability | Connection | Started |",
        "|---|--:|--:|--:|",
    ]
    for npc, trait, count in zip(npcs, sociability, started, strict=True):
        lines.append(
            f"| {npc.id} | {trait:.2f} | {npc.values[CoreValue.CONNECTION]:.2f} | {count} |"
        )
    return [
        *lines,
        "",
        f"{sum(started)} conversations, {sum(started) / hours:.2f} per sim hour. Spearman rank "
        f"correlation of sociability with conversations started: "
        f"{spearman(sociability, [float(n) for n in started]):.2f}.",
    ]


def shifts(observer: Observer) -> list[str]:
    economy = observer.economy
    assert economy is not None
    now, grace = observer.behaviour.clock.now, timedelta(minutes=economy.config.late)
    workers = sorted(
        (npc for npc in observer.behaviour.npcs.values() if npc.shifts),
        key=lambda npc: npc.values[CoreValue.RESPONSIBILITY],
    )
    lines = [
        f"**Shifts.** Every shift that ended, by Responsibility: on time, late (more than "
        f"{economy.config.late:g} minutes, and by how long on average), skipped, and hours at "
        "work during them and straight after.",
        "",
        "| NPC | Workplace | Responsibility | Discipline | Shifts | On time | Late | Minutes late "
        "| Skipped | Hours | Overtime |",
        "|---|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    totals = Counter[str]()
    for npc in workers:
        done = [turn for turn in economy.turns if turn.npc == npc.id and turn.end <= now]
        late = [turn for turn in done if turn.late(grace)]
        skipped = sum(turn.arrived is None for turn in done)
        minutes = [
            (turn.arrived - turn.start) / timedelta(minutes=1) for turn in late if turn.arrived
        ]
        row = {
            "shifts": len(done),
            "on time": len(done) - len(late) - skipped,
            "late": len(late),
            "skipped": skipped,
        }
        totals.update(row)
        lines.append(
            f"| {npc.id} | {npc.workplace} | {npc.values[CoreValue.RESPONSIBILITY]:.2f} | "
            f"{npc.values[CoreValue.DISCIPLINE]:.2f} | {row['shifts']} | {row['on time']} | "
            f"{row['late']} | {sum(minutes) / len(minutes) if minutes else 0:.0f} | {skipped} | "
            f"{sum(turn.worked for turn in done):.1f} | {sum(turn.overtime for turn in done):.1f} |"
        )
    lines.append(
        f"| **All** | | | | {totals['shifts']} | {totals['on time']} | {totals['late']} | | "
        f"{totals['skipped']} | | |"
    )
    return lines


def money(observer: Observer) -> list[str]:
    economy = observer.economy
    assert economy is not None
    behaviour = observer.behaviour
    earned: Counter[Id] = Counter()
    spent: Counter[Id] = Counter()
    for entry in economy.ledger.entries:
        earned[entry.payee] += entry.amount
        spent[entry.payer] += entry.amount
    samples = max((len(v) for v in observer.money.values()), default=0)
    times = [f"{n * MONEY_EVERY / timedelta(hours=1):g} h" for n in range(samples)]
    lines = [
        f"**Money.** Each resident's money every {MONEY_EVERY / timedelta(hours=1):g} sim hours "
        "from the start, at the end and the least they had, what came in and went out, and their "
        "savings target.",
        "",
        "| NPC | Pay | Target | " + " | ".join(times) + " | End | Least | In | Out |",
        "|---|---|--:|" + "--:|" * (samples + 4),
    ]
    for npc in sorted(behaviour.npcs.values(), key=lambda npc: npc.id):
        pay = "-" if npc.pay is None else npc.pay.kind.value
        if npc.pay and npc.pay.amount:
            pay += f" {npc.pay.amount:g}"
        cells = [f"{amount:.0f}" for amount in observer.money[npc.id]]
        lines.append(
            f"| {npc.id} | {pay} | {behaviour.savings(npc.id):.0f} | "
            + " | ".join(cells)
            + f" | {economy.money[npc.id]:.0f} | {observer.least.get(npc.id, 0.0):.0f} | "
            f"{earned[npc.id]:.0f} | {spent[npc.id]:.0f} |"
        )
    return lines


def ledger(observer: Observer) -> list[str]:
    from simile.economy import OUTSIDE, Kind

    economy = observer.economy
    assert economy is not None
    book = economy.ledger
    kinds = book.by_kind()
    between: Counter[str] = Counter()
    for entry in book.entries:
        if entry.kind is Kind.PURCHASE:
            between[entry.place or "-" if entry.payee != OUTSIDE else OUTSIDE] += entry.amount
    unrun = between.pop(OUTSIDE, 0.0)
    rows = [
        ("in", "wages", kinds[Kind.WAGE]),
        ("in", "pensions", kinds[Kind.PENSION]),
        ("out", "rent", kinds[Kind.RENT]),
        ("out", "groceries", kinds[Kind.GROCERIES]),
        ("out", "supplies", kinds[Kind.SUPPLIES]),
        ("out", "shops nobody runs", unrun),
        *(("between", f"at {place}", amount) for place, amount in sorted(between.items())),
    ]
    came_in, went_out = book.came_in(), book.went_out()
    change = sum(economy.money.values()) - sum(book.opening.values())
    return [
        "**Where the money went.** Every movement in the ledger: in from outside the village, out "
        "of it, and between residents.",
        "",
        "| | | Amount |",
        "|---|---|--:|",
        *(f"| {flow} | {what} | {amount:.0f} |" for flow, what, amount in rows),
        "",
        f"In minus out: {came_in - went_out:.2f}. The change in what residents hold: "
        f"{change:.2f}. Gap: {book.gap(economy.money):.2f}.",
    ]


def shares(observer: Observer) -> list[str]:
    awake = sum(observer.awake_at.values()) or 1
    return [
        "**Time by place.** Share of waking resident-minutes in each place.",
        "",
        "| " + " | ".join(PLACES) + " |",
        "|" + "--:|" * len(PLACES),
        "| " + " | ".join(f"{observer.awake_at[place] / awake:.1%}" for place in PLACES) + " |",
    ]


def spots(observer: Observer) -> list[str]:
    places = [place for place in PLACES if observer.stays[place]]
    return [
        "**Spots.** Share of each place's stay time, awake and not walking, spent on a spot.",
        "",
        "| " + " | ".join(places) + " |",
        "|" + "--:|" * len(places),
        "| " + " | ".join(f"{observer.on_spot[p] / observer.stays[p]:.0%}" for p in places) + " |",
    ]


def meals(observer: Observer, hours: float) -> list[str]:
    if not observer.meals:
        return ["**Meals.** None."]
    places = sorted({meal.place for meal in observer.meals})
    by_hour: dict[int, Counter[str]] = defaultdict(Counter)
    for meal in observer.meals:
        by_hour[meal.at.hour][meal.place] += 1
    count, residents = len(observer.meals), len(observer.behaviour.npcs)
    hunger = sum(meal.hunger for meal in observer.meals) / count
    lines = [
        f"**Meals.** Times hunger fell by at least {MEAL:g} in one go: {count}, or "
        f"{count / residents / hours * 24:.1f} per resident per sim-day, starting at a hunger "
        f"of {hunger:.2f} on average. By the hour they started eating, and where.",
        "",
        "| Hour | " + " | ".join(places) + " |",
        "|--:|" + "--:|" * len(places),
    ]
    for hour in sorted(by_hour):
        cells = [str(by_hour[hour][place] or "·") for place in places]
        lines.append(f"| {hour:02d} | " + " | ".join(cells) + " |")
    return lines


def needs(observer: Observer) -> list[str]:
    lines = [
        "**Needs.** Every resident's needs once a sim minute: the mean, the most, and the share of "
        "their waking and sleeping time at 0.9 or more.",
        "",
        "| Need | Mean | Most | 0.9+ awake | 0.9+ asleep |",
        "|---|--:|--:|--:|--:|",
    ]
    for need, samples in observer.needs.items():
        values = [value for value, _ in samples]
        high = [_share([v >= 0.9 for v, awake in samples if awake is up]) for up in (True, False)]
        lines.append(
            f"| {need} | {sum(values) / len(values):.2f} | {max(values):.2f} | {high[0]} | "
            f"{high[1]} |"
        )
    return lines


def _share(hits: list[bool]) -> str:
    return f"{sum(hits) / len(hits):.1%}" if hits else "-"


def works(observer: Observer, hours: float) -> list[str]:
    crafters = sorted(
        (npc for npc in observer.behaviour.npcs.values() if npc.craft),
        key=lambda npc: -npc.values[CoreValue.CREATIVITY],
    )
    if not crafters:
        return ["**Works.** Nobody has a craft."]
    lines = [
        "**Works.** What each resident with a craft made, where, and the share of their waking "
        "time spent making it. Muralists paint the map's walls in turn.",
        "",
        "| NPC | Craft | Creativity | Self-actualization | Works | Per sim-day | Where | Making |",
        "|---|---|--:|--:|--:|--:|---|--:|",
    ]
    for npc in crafters:
        made = observer.works[npc.id]
        count = sum(made.values())
        where = ", ".join(f"{place} {n}" for place, n in made.most_common()) or "-"
        awake = observer.awake[npc.id]
        making = f"{observer.creating[npc.id] / awake:.0%}" if awake else "-"
        lines.append(
            f"| {npc.id} | {_medium(npc)} | {npc.values[CoreValue.CREATIVITY]:.2f} | "
            f"{npc.values[CoreValue.SELF_ACTUALIZATION]:.2f} | {count} | "
            f"{count / hours * 24:.1f} | {where} | {making} |"
        )
    return lines


GOALS = tuple(a for a in Activity if a is not Activity.TALK)


def _count(value: float) -> str:
    return f"{value:.1f}" if value else "·"


def _medium(npc: Npc) -> Medium | None:
    return npc.craft.medium if npc.craft else None
