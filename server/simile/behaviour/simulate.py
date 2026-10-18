import math
import random
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterable, Mapping
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from starlette.applications import Starlette

from simile.behaviour.config import Activity, Need
from simile.behaviour.events import GoalChosen, IntentionBroken, IntentionKept
from simile.behaviour.intentions import reliability
from simile.behaviour.mind import Behaviour, create_behaviour, no_conversations
from simile.behaviour.scoring import Goal, MuralSpot
from simile.memory import MemoryStore
from simile.schema import (
    CoreValue,
    Id,
    Intention,
    IntentionKind,
    LocationKind,
    Medium,
    Memory,
    MemoryKind,
    Npc,
    Traits,
)
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
STARVING = 0.9
TOPICS = (
    "rent",
    "fair pay",
    "the river",
    "drone deliveries",
    "the council",
    "coffee",
    "street art",
    "poetry",
    "painting",
    "tradition",
    "football",
    "night markets",
    "new ideas",
    "safety",
    "freedom",
    "community",
)
"""The stand-in memories' topics, some touching a craft or a value."""
LATER = (1.0, 6.0)
"""How many sim hours ahead a seeded intention for later falls due."""
EXPIRE_NOW = timedelta(hours=2)
EXPIRE_LATER = timedelta(days=1)
"""As B3's `expire_now` and `expire_later`."""


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
    shops: dict[str, Counter[str]] = field(default_factory=lambda: defaultdict(Counter))
    """Minutes each shop's keeper was due on shift, it was staffed, sold out while staffed, and
    staffed outside their shifts."""
    fridges: dict[Id, list[int]] = field(default_factory=lambda: defaultdict(list))
    """Each home's fridge once a sim minute."""
    starving: dict[Id, int] = field(default_factory=dict)
    """How many minutes in a row each resident has been awake at a hunger of `STARVING` or more."""
    longest: dict[Id, int] = field(default_factory=dict)
    """Each resident's longest such stretch."""
    memory: MemoryStore | None = None
    """Where reading and talking leave stand-in memories, which raise crafters' inspiration."""
    rng: random.Random = field(default_factory=random.Random)
    made: list[tuple[datetime, Id]] = field(default_factory=list)
    """When each work was made, and by whom."""
    stays: Counter[str] = field(default_factory=Counter)
    """Minutes staying in each place out of home: there, awake and not walking."""
    on_spot: Counter[str] = field(default_factory=Counter)
    """Of those, minutes on a spot."""
    intentions: float | None = None
    """Sim hours between each round of seeded intentions, or None for none."""
    intended: Counter[Id] = field(default_factory=Counter)
    kept: Counter[Id] = field(default_factory=Counter)
    broken: Counter[Id] = field(default_factory=Counter)
    late: list[float] = field(default_factory=list)
    """Minutes from each kept intention falling due to its being kept."""
    overdue: timedelta = timedelta()
    """The longest any intention was seen open past its expiry."""

    def __post_init__(self) -> None:
        self.start = self.next = self.behaviour.clock.now
        self.next_money = self.next_intentions = self.next

    def request_conversation(self, a: Id, b: Id) -> bool:
        if self.talk is None:
            return False
        self.started[a] += 1
        self.ending.append((self.behaviour.clock.now + timedelta(minutes=self.talk), a, b))
        return True

    def on_goal(self, event: GoalChosen) -> None:
        self.goals[event.npc][event.activity] += 1

    def on_kept(self, event: IntentionKept) -> None:
        intention = event.intention
        self.kept[intention.owner] += 1
        late = (self.behaviour.clock.now - intention.due) / timedelta(minutes=1)
        self.late.append(max(late, 0.0))

    def on_broken(self, event: IntentionBroken) -> None:
        self.broken[event.intention.owner] += 1

    def intend(self, now: datetime) -> None:
        """Each resident who's awake says they'll do something to someone, at random: make
        something, go somewhere, look someone up or read the news, now or later."""
        behaviour, rng = self.behaviour, self.rng
        residents = sorted(behaviour.npcs)
        for npc in residents:
            if behaviour.minds[npc].goal.activity is Activity.SLEEP:
                continue
            options = behaviour.options(npc)
            others = [other for other in residents if other != npc]
            kinds = [IntentionKind.GO, IntentionKind.SEEK, IntentionKind.NEWS]
            if options.medium is not None:
                kinds.append(IntentionKind.CREATE)
            kind = rng.choice(kinds)
            target = {
                IntentionKind.GO: rng.choice(sorted(options.places)),
                IntentionKind.SEEK: rng.choice(others),
            }.get(kind)
            later = rng.random() < 0.5
            due = now + timedelta(hours=rng.uniform(*LATER)) if later else now
            self.intended[npc] += behaviour.intend(
                Intention(
                    id=f"seeded/{npc}/{sum(self.intended.values())}",
                    owner=npc,
                    kind=kind,
                    target=target,
                    description=f"a seeded {kind.value}",
                    promised_to=[rng.choice(others)],
                    created=now,
                    due=due,
                    expires=due + (EXPIRE_LATER if later else EXPIRE_NOW),
                )
            )

    def on_create(self, npc: Npc, wall: Id | None, intention: Intention | None = None) -> None:
        target = self.behaviour.goal(npc.id).target
        self.works[npc.id][wall or (HOME if target == npc.home else str(target))] += 1
        self.made.append((self.behaviour.clock.now, npc.id))

    def read_news(self, npc: Npc) -> None:
        self.remember(npc.id, MemoryKind.NEWS)

    def remember(self, npc: Id, kind: MemoryKind, about: Id | None = None) -> None:
        """A stand-in for the memory a talk or an article leaves, of middling strength."""
        if self.memory is None:
            return
        rng = self.rng
        self.memory.add(
            Memory(
                owner=npc,
                kind=kind,
                content=f"A stand-in {kind.value} memory.",
                salience=rng.uniform(0.2, 0.8),
                valence=rng.uniform(-0.7, 0.7),
                timestamp=self.behaviour.clock.now,
                about=[about] if about else [],
                topics=rng.sample(TOPICS, 2),
            )
        )

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
            _, a, b = over
            for npc, other in ((a, b), (b, a)):
                self.behaviour.resume(npc)
                self.remember(npc, MemoryKind.CONVERSATION, other)
        if self.intentions is not None and clock.now >= self.next_intentions:
            self.next_intentions += timedelta(hours=self.intentions)
            self.intend(clock.now)
        if clock.now < self.next:
            return
        self.next += self.every
        for intention in self.behaviour.intentions():
            self.overdue = max(self.overdue, clock.now - intention.expires)
        self.serve(clock.now)
        self.sample_money(clock.now)
        self.sample_stock(clock.now)
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

    def sample_stock(self, now: datetime) -> None:
        economy = self.economy
        if economy is None:
            return
        for place, keeper in economy.keepers.items():
            counts = self.shops[place]
            shift = any(shift.covers(now) for shift in self.behaviour.npcs[keeper].shifts)
            staffed = economy.staffed(place)
            counts["shift"] += shift
            counts["staffed"] += staffed
            counts["sold out"] += staffed and not economy.serving(place)
            counts["outside"] += staffed and not shift
        for home, left in economy.fridges.items():
            self.fridges[home].append(left)

    def sample_needs(self, npc: Npc, place: str) -> None:
        mind = self.behaviour.minds[npc.id]
        awake = mind.goal.activity is not Activity.SLEEP
        for need, value in mind.needs.items():
            if npc.craft or need is not Need.INSPIRATION:
                self.needs[need].append((value, awake))
        starving = awake and mind.needs[Need.HUNGER] >= STARVING
        self.starving[npc.id] = self.starving.get(npc.id, 0) + 1 if starving else 0
        self.longest[npc.id] = max(self.longest.get(npc.id, 0), self.starving[npc.id])
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
    intentions: float | None = None,
) -> tuple[Observer, float]:
    """Run memory, world, behaviour and E3's economy for `hours` of sim time as fast as the CPU
    allows, with N1's NPCs and the cast's traits unless given others, on an in-memory store. The
    economy says which shops are staffed and what's left to eat, and the Daily Grind serves
    whoever arrives while its barista is at work, as G1 would. Conversations, news and works stay
    stubbed, so nothing calls Claude: every request to talk is declined, or with `talk` accepted
    and over after that many minutes, there's always an article of `NEWS_INTEREST` to read,
    muralists paint the map's walls in turn, and making something does nothing. Each article read
    and each talk leaves a stand-in memory, which raises a crafter's inspiration. With
    `intentions`, every that many sim hours each resident awake says they'll do something at
    random."""
    from simile.behaviour.lifespan import lifespan as behaviour
    from simile.cafe.config import DEFAULT_CONFIG as CAFE
    from simile.economy.economy import economy_of
    from simile.economy.lifespan import lifespan as economy
    from simile.memory.lifespan import lifespan as memory
    from simile.world.lifespan import lifespan as world_lifespan

    app = Starlette()
    world = World(Clock(start), FakeWallClock())
    app.state.world = world
    app.state.headless = True
    app.state.memory = MemoryStore(":memory:")
    app.state.behaviour = create_behaviour(app, seed=seed, npcs=npcs, traits=traits)
    shops = economy_of(app)
    observer = Observer(
        app.state.behaviour,
        talk=talk,
        economy=shops,
        open=lambda: shops.staffed(CAFE.home),
        memory=app.state.memory,
        rng=random.Random(seed),
        intentions=intentions,
    )
    world.bus.subscribe(GoalChosen, observer.on_goal)
    world.bus.subscribe(IntentionKept, observer.on_kept)
    world.bus.subscribe(IntentionBroken, observer.on_broken)
    started = time.perf_counter()
    async with AsyncExitStack() as stack:
        for hook in (behaviour, economy, memory, world_lifespan):
            await stack.enter_async_context(hook(app))
        app.state.behaviour.hooks.set(
            request_conversation=observer.request_conversation,
            read_news=observer.read_news,
            news_interest=lambda npc: NEWS_INTEREST,
            conversations=no_conversations,
            create=observer.on_create,
            mural_wall=observer.mural_wall,
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
    lines += ["", *shares(observer), "", *meals(observer, hours), "", *needs(observer)]
    lines += ["", *hunger(observer)]
    lines += ["", *works(observer, hours)]
    lines += ["", *spots(observer)]
    if observer.talk is not None:
        lines += ["", *conversations(observer, hours)]
    if observer.intentions is not None:
        lines += ["", *intentions(observer)]
    if observer.economy is not None:
        lines += ["", *shifts(observer), "", *shops(observer), "", *fridges(observer)]
        lines += ["", *money(observer), "", *ledger(observer)]
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


def intentions(observer: Observer) -> list[str]:
    behaviour = observer.behaviour
    npcs = sorted(behaviour.npcs.values(), key=lambda npc: reliability(npc.values))
    scores = [reliability(npc.values) for npc in npcs]
    lines = [
        f"**Intentions.** Every {observer.intentions:g} sim hours each resident awake said they'd "
        "do something at random, half of them now and half within "
        f"{LATER[0]:g} to {LATER[1]:g} hours, to expire {EXPIRE_NOW / timedelta(hours=1):g} hours "
        f"after it's due for now and {EXPIRE_LATER / timedelta(hours=1):g} for later. By "
        "reliability (Responsibility and Discipline): how many each took on, kept, broke by "
        "letting them expire, and still had open at the end.",
        "",
        "| NPC | Responsibility | Discipline | Reliability | Taken on | Kept | Broken | Open | "
        "Kept share |",
        "|---|--:|--:|--:|--:|--:|--:|--:|--:|",
    ]
    shares = []
    for npc, score in zip(npcs, scores, strict=True):
        kept, broken = observer.kept[npc.id], observer.broken[npc.id]
        done = kept + broken
        share = kept / done if done else 0.0
        shares.append(share)
        lines.append(
            f"| {npc.id} | {npc.values[CoreValue.RESPONSIBILITY]:.2f} | "
            f"{npc.values[CoreValue.DISCIPLINE]:.2f} | {score:.2f} | {observer.intended[npc.id]} | "
            f"{kept} | {broken} | {len(behaviour.intentions(npc.id))} | "
            + (f"{share:.0%} |" if done else "- |")
        )
    kept, broken = sum(observer.kept.values()), sum(observer.broken.values())
    late = sorted(observer.late)
    median = late[len(late) // 2] if late else 0.0
    return [
        *lines,
        "",
        f"{kept} kept and {broken} broken, {kept / (kept + broken or 1):.0%} kept. Spearman rank "
        f"correlation of reliability with the share kept: {spearman(scores, shares):.2f}. Kept a "
        f"median of {median:.0f} sim minutes after falling due. The longest any intention was "
        f"seen open past its expiry: {observer.overdue.total_seconds():.0f} sim seconds.",
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


def shops(observer: Observer) -> list[str]:
    economy = observer.economy
    assert economy is not None
    now = observer.behaviour.clock.now
    lines = [
        "**Shops.** Hours each shop's keeper was due on shift, the shop was staffed (from when "
        "they arrived until the shift ended), sold out while staffed, and staffed outside their "
        "shifts. The shifts they skipped, and every batch cooked.",
        "",
        "| Shop | Keeper | On shift | Staffed | Sold out | Outside shifts | Shifts | Skipped |",
        "|---|---|--:|--:|--:|--:|--:|--:|",
    ]
    for place, keeper in sorted(economy.keepers.items()):
        counts = observer.shops[place]
        done = [turn for turn in economy.turns if turn.npc == keeper and turn.end <= now]
        skipped = sum(turn.arrived is None for turn in done)
        hours = [counts[key] * observer.every / timedelta(hours=1) for key in SHOP_TIMES]
        cells = " | ".join(f"{h:.1f}" for h in hours)
        lines.append(f"| {place} | {keeper} | {cells} | {len(done)} | {skipped} |")
    batches = economy.cooked
    sold_out = sum(batch.sold_out is not None for batch in batches)
    lines += [
        "",
        "| Shop | Shift | Cooked | Sold | Sold out at | Gone off |",
        "|---|---|--:|--:|--:|--:|",
        *(
            f"| {b.shop} | {b.shift:%a %H:%M} | {b.cooked} | {b.cooked - b.left - b.gone_off} | "
            f"{f'{b.sold_out:%H:%M}' if b.sold_out else '-'} | {b.gone_off} |"
            for b in batches
        ),
        "",
        f"{sold_out} of {len(batches)} batches sold out.",
    ]
    return lines


SHOP_TIMES = ("shift", "staffed", "sold out", "outside")


def fridges(observer: Observer) -> list[str]:
    from simile.economy import Kind

    economy = observer.economy
    assert economy is not None
    orders = [entry for entry in economy.ledger.entries if entry.kind is Kind.GROCERIES]
    spent = sum(entry.amount for entry in orders)
    empty = sum(left == 0 for levels in observer.fridges.values() for left in levels)
    least = min((min(levels) for levels in observer.fridges.values() if levels), default=0)
    return [
        f"**Fridges.** {len(orders)} grocery orders from {len(economy.fridges)} homes, "
        f"{spent / economy.config.groceries:.0f} meals' worth for {spent:.0f}. The lowest any "
        f"fridge got: {least} meals. Hours fridges were empty: "
        f"{empty * observer.every / timedelta(hours=1):.1f}.",
    ]


def hunger(observer: Observer) -> list[str]:
    longest = sorted(observer.longest.items(), key=lambda item: (-item[1], item[0]))
    worst = ", ".join(f"{npc} {minutes}" for npc, minutes in longest[:3] if minutes) or "nobody"
    return [
        f"**Hunger.** The longest anyone spent awake in one go at a hunger of {STARVING:g} or "
        f"more, in minutes, worst first: {worst}.",
    ]


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
    return [*lines, "", pace(observer, hours)]


def pace(observer: Observer, hours: float) -> str:
    """When the first work came, and how many came a sim hour after it."""
    times = sorted(at for at, _ in observer.made)
    if not times:
        return "No works."
    first = (times[0] - observer.start) / timedelta(hours=1)
    rest = hours - first
    rate = f"{(len(times) - 1) / rest:.2f} a sim hour" if rest > 0 else "-"
    return (
        f"{len(times)} works. The first after {first * 60:.0f} sim minutes, then {rate} "
        f"({len(times) - 1} in {rest:.1f} sim hours)."
    )


GOALS = tuple(a for a in Activity if a is not Activity.TALK)


def _count(value: float) -> str:
    return f"{value:.1f}" if value else "·"


def _medium(npc: Npc) -> Medium | None:
    return npc.craft.medium if npc.craft else None
