import asyncio
import heapq
import itertools
import math
import random
import re
import statistics
from collections import Counter, deque
from collections.abc import AsyncGenerator, Callable, Iterable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from starlette.applications import Starlette

from simile.ambient.config import DEFAULT_CONFIG, AmbientConfig
from simile.ambient.director import Earshot
from simile.ambient.events import Nudged
from simile.behaviour import Activity
from simile.conversation import LineDrafted
from simile.conversation.player import DEFAULT_PLAYER_CONFIG
from simile.llm import CallRecord, LLMClient, Request, Usage
from simile.protocol import PlayerMoveMessage, PlayerSayMessage, Position
from simile.reflection.extraction import SYSTEM as REFLECTING
from simile.schema import PLAYER_ID, CoreValue, Id, Npc
from simile.sim import (
    Clock,
    ConversationEnded,
    ConversationStarted,
    FakeWallClock,
    LineSpoken,
    World,
)
from simile.world.paths import Cell, find_path

START = datetime(2026, 10, 16, 9, 30, tzinfo=UTC)
ROUTE = ("square", "coffee_shop", "maker_space", "park", "square", "noodle_bar")
PLAYER_SPEED = 2.6
"""Tiles per second, the client's `PLAYER_SPEED`."""
SAY_RANGE = 3.0
"""The chat box picks NPCs within this many tiles."""
LOOK = 12.0
"""How far the player looks for someone to walk up to."""
AGAIN = timedelta(minutes=10)
"""How long before the player walks up to someone they've talked to again."""

WORDS = 33
"""Words in a line from Claude, on average, in D2's soak."""
TOP_VALUES, ON_TOPIC = 5, 0.6
"""The chance each value a line touches is one of the speaker's top five, as in D2."""
LINE, REPLY, REFLECTION, OTHER = 3.1, (1.1, 0.9), 13.9, 3.0
"""Sim seconds Claude takes to write each, at 1x: I4's medians."""

PHRASES = (
    "the bakery had fresh rolls again this morning",
    "I keep meaning to fix the gate by the allotments",
    "the light over the square was lovely today",
    "my neighbour lent me a ladder last week",
    "the river looked high after all that rain",
    "there is a new mural going up near the station",
    "I tried that recipe with lemons and thyme",
    "the market stalls were busier than usual",
    "the kids from the school painted the benches",
    "somebody left a box of apples by the fountain",
    "the old clock on the hall is running slow again",
    "I found a book about the canal in the library",
)
HELLO = "Hi there! How's your day going?"
SAY = (
    "Oh nice. What have you been up to this morning?",
    "Ha, fair enough. Is it always this quiet around here?",
    "What do you make of the village these days?",
    "I'm still finding my way around. Any tips?",
    "That sounds lovely. Who should I meet next?",
)
BYE = "Anyway, I'd better get on. Bye for now!"
SPEAKER = re.compile(r"You are (.+?), aged")


class Delays:
    """Sleeps that end in sim time. Tick it on the sim loop."""

    def __init__(self, clock: Clock) -> None:
        self.clock = clock
        self._waiting: list[tuple[datetime, int, asyncio.Future[None]]] = []
        self._order = itertools.count()

    async def wait(self, seconds: float) -> None:
        future = asyncio.get_running_loop().create_future()
        due = self.clock.now + timedelta(seconds=seconds)
        heapq.heappush(self._waiting, (due, next(self._order), future))
        await future

    def tick(self, dt: float) -> None:
        while self._waiting and self._waiting[0][0] <= self.clock.now:
            future = heapq.heappop(self._waiting)[2]
            if not future.done():
                future.set_result(None)

    def close(self) -> None:
        for _, _, future in self._waiting:
            future.cancel()
        self._waiting.clear()


class Padded:
    """A fake LLM whose lines are as long as Claude's, touch values as Claude's do, and take as
    long to write at 1x. Reflections store nothing."""

    name = "padded"

    def __init__(self, npcs: Iterable[Npc], delays: Delays, rng: random.Random) -> None:
        self.npcs = {npc.name: npc for npc in npcs}
        self.delays = delays
        self.rng = rng

    async def stream(self, request: Request) -> AsyncGenerator[str | Usage, None]:
        steps = self._steps(request)
        text = ""
        for delay, chunk in steps:
            await self.delays.wait(delay)
            text += chunk
            yield chunk
        yield Usage(
            input_tokens=sum(len(m.content.split()) for m in request.messages),
            output_tokens=len(text.split()),
            model=f"padded-{request.model}",
        )

    def _steps(self, request: Request) -> list[tuple[float, str]]:
        if request.system.startswith(REFLECTING):
            return [(REFLECTION, '{"reflections": []}')]
        found = SPEAKER.match(request.system)
        npc = self.npcs.get(found.group(1)) if found else None
        if npc is None:
            return [(OTHER, self.sentences(WORDS, 1))]
        tag = f"\n[values: {', '.join(self.values(npc))}]"
        if request.model == DEFAULT_PLAYER_CONFIG.model:
            first, rest = self.sentences(WORDS, 2).split("\n")
            return [(REPLY[0], first + " "), (REPLY[1], rest + tag)]
        return [(LINE, self.sentences(WORDS, 2).replace("\n", " ") + tag)]

    def sentences(self, words: int, count: int) -> str:
        """`count` sentences of about `words` words in all, one a line."""
        each = math.ceil(words / count)
        out = []
        for _ in range(count):
            picked: list[str] = []
            while len(picked) < each:
                picked += self.rng.choice(PHRASES).split()
                if len(picked) < each:
                    picked.append(self.rng.choice(("and", "but", "so")))
            text = " ".join(picked[:each])
            out.append(text[0].upper() + text[1:] + ".")
        return "\n".join(out)

    def values(self, npc: Npc) -> list[str]:
        ranked = sorted(npc.values, key=lambda value: -npc.values[value])
        top, rest = ranked[:TOP_VALUES], ranked[TOP_VALUES:]
        picked: list[CoreValue] = []
        while len(picked) < 2:
            value = self.rng.choice(top if self.rng.random() < ON_TOPIC else rest)
            if value not in picked:
                picked.append(value)
        return [value.value.replace("_", " ") for value in picked]


class ScriptedPlayer:
    """A connected client whose player walks `route` round and round, lingering at each stop.
    Now and then they walk up to someone and chat, and they answer whoever greets them, a few
    lines each, then say goodbye. Tick it on the sim loop."""

    def __init__(
        self,
        app: Starlette,
        rng: random.Random,
        *,
        route: Sequence[str] = ROUTE,
        chat: float = 0.5,
        linger: tuple[float, float] = (45, 120),
        turns: tuple[int, int] = (2, 4),
        typing: tuple[float, float] = (4, 10),
    ) -> None:
        from simile.behaviour import behaviour_of
        from simile.conversation import conversations_of
        from simile.protocol import hub_of
        from simile.sim import world_of
        from simile.world import movement_of

        self.hub, self.engine = hub_of(app), conversations_of(app)
        self.behaviour, self.movement = behaviour_of(app), movement_of(app)
        self.clock, bus = world_of(app).clock, world_of(app).bus
        self.rng, self.chat, self.linger, self.turns, self.typing = rng, chat, linger, turns, typing
        self.stops = itertools.cycle([*route[1:], route[0]])
        entry = self.movement.town.location(route[0]).entry
        self.position: tuple[float, float] = (entry.x, entry.y)
        self.path: deque[Cell] = deque()
        self.lingering: datetime | None = None
        self.chat_at: datetime | None = None
        self.going_to: Id | None = None
        self.talk: str | None = None
        self.partner: Id | None = None
        self.lines: deque[str] = deque()
        self.pending: set[int] = set()
        self.reply_at: datetime | None = None
        self.bye_at: datetime | None = None
        self.talked: dict[Id, datetime] = {}
        self._stops = [
            bus.subscribe(ConversationStarted, self._on_started),
            bus.subscribe(ConversationEnded, self._on_ended),
            bus.subscribe(LineDrafted, self._on_drafted),
            bus.subscribe(LineSpoken, self._on_spoken),
        ]

    def join(self) -> None:
        self.hub.connections.add(self)  # type: ignore[arg-type]
        self._send_position()
        self._linger()

    def leave(self) -> None:
        self.hub.connections.discard(self)  # type: ignore[arg-type]
        for stop in self._stops:
            stop()

    def put(self, frame: object) -> None:
        pass

    def tick(self, dt: float) -> None:
        now = self.clock.now
        if self.talk is not None:
            self._converse(now)
        elif self.path:
            self._walk(PLAYER_SPEED * dt)
            if not self.path:
                self._arrive()
        elif self.chat_at is not None and now >= self.chat_at:
            self.chat_at = None
            self._approach()
        elif self.lingering is None or now >= self.lingering:
            self._head_for(next(self.stops))

    def _converse(self, now: datetime) -> None:
        if self.bye_at is not None and now >= self.bye_at + timedelta(seconds=30):
            self._done_talking()
        elif self.lines and not self.pending and self.reply_at and now >= self.reply_at:
            self.reply_at = None
            self._say(self.lines.popleft())
            if not self.lines:
                self.bye_at = now

    def _approach(self) -> None:
        now = self.clock.now
        nearby = sorted(
            (distance, npc)
            for npc in self.behaviour.npcs
            if (distance := self._distance(npc)) <= LOOK
            and now >= self.talked.get(npc, now - AGAIN) + AGAIN
            and not self.engine.talking(npc)
            and self.behaviour.goal(npc).activity not in (Activity.HOME, Activity.SLEEP)
        )
        if not nearby:
            return
        distance, npc = nearby[0]
        if distance <= SAY_RANGE:
            self._greet(npc)
        else:
            self.going_to = npc
            self._set_path(self._beside(npc))

    def _greet(self, npc: Id) -> None:
        self.lines, self.partner = self._script(), npc
        self._say(HELLO)
        if self.talk is None:
            self.lines.clear()
            self.partner = None

    def _arrive(self) -> None:
        npc, self.going_to = self.going_to, None
        if npc is not None:
            if self._distance(npc) <= SAY_RANGE + 1 and not self.engine.talking(npc):
                self._greet(npc)
            return
        self._linger()

    def _linger(self) -> None:
        now = self.clock.now
        self.lingering = now + timedelta(seconds=self.rng.uniform(*self.linger))
        wants = self.rng.random() < self.chat
        self.chat_at = now + timedelta(seconds=self.rng.uniform(3, 15)) if wants else None

    def _head_for(self, location: str) -> None:
        area = self.movement.town.location(location).area
        cells = [
            (x, y)
            for x in range(area.x, area.x + area.width)
            for y in range(area.y, area.y + area.height)
            if self.movement.town.walkable(x, y)
        ]
        self._set_path(self.rng.choice(cells))

    def _beside(self, npc: Id) -> Cell:
        there = self.movement.position(npc)
        cells = [
            cell
            for dx, dy in ((-1, 0), (1, 0), (0, -1), (0, 1), (-1, -1), (1, 1), (-1, 1), (1, -1))
            if self.movement.town.walkable(*(cell := (round(there.x) + dx, round(there.y) + dy)))
        ]
        return cells[0] if cells else (round(there.x), round(there.y))

    def _set_path(self, goal: Cell) -> None:
        here = (round(self.position[0]), round(self.position[1]))
        self.path = deque((find_path(self.movement.town, here, goal) or [])[1:])
        if not self.path:
            self._arrive()

    def _walk(self, budget: float) -> None:
        moved = False
        while self.path and budget > 0:
            gap = math.dist(self.position, self.path[0])
            step = min(budget, gap)
            budget -= step
            moved = True
            if step == gap:
                self.position = self.path.popleft()
            else:
                (x0, y0), (x1, y1) = self.position, self.path[0]
                self.position = (x0 + (x1 - x0) * step / gap, y0 + (y1 - y0) * step / gap)
        if moved:
            self._send_position()

    def _say(self, text: str) -> None:
        assert self.partner is not None
        self.hub.receive(PlayerSayMessage(text=text, target=self.partner).model_dump_json())

    def _send_position(self) -> None:
        x, y = self.position
        self.hub.receive(PlayerMoveMessage(position=Position(x=x, y=y)).model_dump_json())

    def _script(self) -> deque[str]:
        return deque([*self.rng.sample(SAY, k=self.rng.randint(*self.turns)), BYE])

    def _distance(self, npc: Id) -> float:
        there = self.movement.position(npc)
        return math.dist(self.position, there)

    def _on_started(self, event: ConversationStarted) -> None:
        participants = event.conversation.participants
        if PLAYER_ID not in participants:
            return
        self.talk = event.conversation.id
        self.partner = next(p for p in participants if p != PLAYER_ID)
        self.pending.clear()
        self.reply_at = self.bye_at = None
        if not self.lines:
            self.lines = self._script()

    def _on_ended(self, event: ConversationEnded) -> None:
        if event.conversation.id == self.talk:
            assert self.partner is not None
            self.talked[self.partner] = self.clock.now
            self._done_talking()

    def _done_talking(self) -> None:
        self.talk = self.partner = self.reply_at = self.bye_at = None
        self.lines.clear()
        self.pending.clear()

    def _on_drafted(self, event: LineDrafted) -> None:
        if event.line.conversation_id == self.talk and event.line.speaker != PLAYER_ID:
            self.pending.add(event.line.id)

    def _on_spoken(self, event: LineSpoken) -> None:
        line = event.line
        if line.conversation_id != self.talk or line.speaker == PLAYER_ID:
            return
        self.pending.discard(line.id)
        ends = line.timestamp + timedelta(seconds=line.duration)
        self.reply_at = ends + timedelta(seconds=self.rng.uniform(*self.typing))


@dataclass
class Result:
    minutes: float
    heard: float = 0.0
    """Sim seconds with an NPC conversation in earshot."""
    longest_quiet: float = 0.0
    """The longest stretch without one, in sim seconds."""
    overheard: set[str] = field(default_factory=set)
    """NPC conversations the player heard at least a line of."""
    lines_overheard: int = 0
    npc_conversations: set[str] = field(default_factory=set)
    player_conversations: set[str] = field(default_factory=set)
    nudges: int = 0
    calls: Counter[str] = field(default_factory=Counter)
    """LLM calls by purpose."""


class Listener:
    """What the player hears, and what it costs. Tick it on the sim loop."""

    def __init__(self, app: Starlette, minutes: float, config: AmbientConfig) -> None:
        from simile.conversation import conversations_of
        from simile.sim import world_of
        from simile.world import movement_of

        self.app, self.result = app, Result(minutes)
        self.movement, bus = movement_of(app), world_of(app).bus
        self.earshot = Earshot(self._from_player, config)
        for conversation in conversations_of(app).live():
            self.earshot.on_started(ConversationStarted(conversation))
        self.quiet, self._elapsed = 0.0, 0.0
        self._stops = [
            bus.subscribe(ConversationStarted, self._on_started),
            bus.subscribe(ConversationEnded, self.earshot.on_ended),
            bus.subscribe(LineSpoken, self._on_spoken),
            bus.subscribe(Nudged, self._on_nudged),
        ]
        self.llm: LLMClient = app.state.llm
        self.llm.listeners.append(self._on_call)

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed < 1 - 1e-9:
            return
        seconds, self._elapsed = self._elapsed, 0.0
        if self.earshot.update():
            self.result.heard += seconds
            self.quiet = 0.0
        else:
            self.quiet += seconds
            self.result.longest_quiet = max(self.result.longest_quiet, self.quiet)

    def stop(self) -> Result:
        for stop in self._stops:
            stop()
        self.llm.listeners.remove(self._on_call)
        return self.result

    def _from_player(self, npc: Id) -> float | None:
        try:
            return self.movement.distance(npc, PLAYER_ID)
        except KeyError:
            return None

    def _on_started(self, event: ConversationStarted) -> None:
        conversation = event.conversation
        self.earshot.on_started(event)
        if PLAYER_ID in conversation.participants:
            self.result.player_conversations.add(conversation.id)
        else:
            self.result.npc_conversations.add(conversation.id)

    def _on_spoken(self, event: LineSpoken) -> None:
        if event.line.conversation_id in self.earshot.heard:
            self.result.overheard.add(event.line.conversation_id)
            self.result.lines_overheard += 1

    def _on_nudged(self, event: Nudged) -> None:
        self.result.nudges += 1

    def _on_call(self, record: CallRecord) -> None:
        self.result.calls[record.purpose] += 1


async def playthrough(
    *,
    minutes: float = 30,
    warmup: float = 60,
    seed: int = 0,
    start: datetime = START,
    prepare: Callable[[Starlette], None] | None = None,
    config: AmbientConfig = DEFAULT_CONFIG,
) -> Result:
    """Run the village on the padded fake LLM for `warmup` sim minutes with nobody connected,
    then for `minutes` with the scripted player, and return what they heard. `prepare` gets the
    app between the two."""
    from simile.app import create_app
    from simile.behaviour.mind import create_behaviour
    from simile.conversation import create_engine

    world = World(Clock(start), FakeWallClock())
    app = create_app()
    app.state.world, app.state.headless = world, True
    app.state.behaviour = create_behaviour(app, seed=seed)
    app.state.conversation = create_engine(app, seed=seed)
    rng = random.Random(seed)
    delays = Delays(world.clock)
    world.loop.register(delays)
    async with app.router.lifespan_context(app):
        app.state.llm = LLMClient(Padded(app.state.behaviour.npcs.values(), delays, rng))
        await world.loop.run(timedelta(minutes=warmup))
        if prepare is not None:
            prepare(app)
        player, listener = ScriptedPlayer(app, rng), Listener(app, minutes, config)
        world.loop.register(player)
        world.loop.register(listener)
        player.join()
        await world.loop.run(timedelta(minutes=minutes))
        result = listener.stop()
        player.leave()
        delays.close()
    return result


def report(results: Sequence[Result]) -> str:
    """The runs' results as a Markdown table: mean, min and max of each measure."""
    rows: list[tuple[str, list[float], str]] = [
        ("NPC conversation in earshot, share of the time", [_share(r) for r in results], "{:.0%}"),
        ("Overheard conversations every 5 minutes", [_per(r, 5) for r in results], "{:.2f}"),
        ("Longest without one, minutes", [r.longest_quiet / 60 for r in results], "{:.1f}"),
        ("Lines overheard", [r.lines_overheard for r in results], "{:.0f}"),
        (
            "NPC conversations per sim hour",
            [len(r.npc_conversations) / r.minutes * 60 for r in results],
            "{:.1f}",
        ),
        ("Player conversations", [len(r.player_conversations) for r in results], "{:.1f}"),
        ("Nudges", [r.nudges for r in results], "{:.1f}"),
    ]
    purposes = sorted({purpose for r in results for purpose in r.calls})
    for purpose in [*purposes, None]:
        name = f"LLM calls per sim hour: {purpose or 'all'}"
        hourly = [
            (r.calls[purpose] if purpose else sum(r.calls.values())) / r.minutes * 60
            for r in results
        ]
        rows.append((name, hourly, "{:.0f}"))
    lines = ["| | Mean | Min | Max |", "|---|--:|--:|--:|"]
    for name, values, form in rows:
        cells = [form.format(v) for v in (statistics.fmean(values), min(values), max(values))]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


def _share(result: Result) -> float:
    return result.heard / (result.minutes * 60)


def _per(result: Result, minutes: float) -> float:
    return len(result.overheard) / result.minutes * minutes
