import asyncio
import itertools
import logging
import math
import random
from collections import deque
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any, Protocol

from starlette.applications import Starlette

from simile.behaviour import Activity, Behaviour, Goal, Need
from simile.cafe import events
from simile.cafe.config import DEFAULT_CONFIG, CafeConfig
from simile.cafe.events import GaveUp, Ordered, Served, Store
from simile.cafe.lines import Lines
from simile.cafe.menu import Drink, Menu, load_menu
from simile.cafe.orders import (
    EXCHANGE_SYSTEM,
    Exchange,
    Order,
    barista_system,
    exchange_prompt,
    order_prompt,
)
from simile.conversation import Cue, LineDrafted, duration
from simile.conversation.player import DEFAULT_PLAYER_CONFIG
from simile.conversation.prompt import first_name
from simile.llm import LLMClient, LLMError, StructuredOutputError
from simile.schema import (
    PLAYER_ID,
    Conversation,
    Id,
    Line,
    Location,
    MapTile,
    Npc,
    Relationship,
    Shift,
)
from simile.sim import Clock, ConversationEnded, ConversationStarted, EventBus, LineSpoken
from simile.social import as_of, meet
from simile.voice import speaking_rate
from simile.voicing.distance import between
from simile.world import Point

logger = logging.getLogger(__name__)

AWAY = (Activity.HOME, Activity.SLEEP)
VISITS = (Activity.COFFEE_SHOP, Activity.CREATE)
SCENE_TIMEOUT = 20.0
FRESH = timedelta(minutes=1)
"""A goal chosen this recently is a new visit. An older one, as from a save, is a stay."""


def barista(npcs: Iterable[Npc], cafe: Id) -> Id | None:
    """Whoever works at the café, as a cast's barista does, else whoever lives there."""
    there = [npc for npc in npcs if cafe in (npc.workplace, npc.home)]
    there.sort(key=lambda npc: npc.workplace != cafe)
    return there[0].id if there else None


class Engine(Protocol):
    """What the café needs from B2's engine."""

    def talking(self, npc: Id) -> bool: ...

    def accept_score(self, a: Id, b: Id) -> float: ...

    def as_voiced(self, line: Line) -> Line: ...

    def still_playing(self, conversation: Conversation) -> datetime | None: ...


class Players(Protocol):
    """What the café needs from B5's player conversations."""

    writers: dict[Id, Any]

    def interject(self, npc: Id, text: str) -> bool: ...


class Phase(StrEnum):
    COMING = "coming"
    QUEUING = "queuing"
    ORDERING = "ordering"
    WAITING = "waiting"
    SITTING = "sitting"


class Step(StrEnum):
    ASKING = "asking"
    TALKING = "talking"
    MAKING = "making"
    HANDING = "handing"


@dataclass
class Visit:
    """A resident at, or on their way to, the café."""

    npc: Id
    goal: Goal
    phase: Phase
    queued: datetime | None = None
    spot: MapTile | None = None
    seat: MapTile | None = None
    stay: timedelta | None = None


@dataclass
class Job:
    """An order the barista is working on."""

    customer: Id
    drink: str
    menu: str | None
    step: Step
    waited_from: datetime
    ready_at: datetime | None = None
    wrong: bool = False
    writing: asyncio.Task[Exchange | None] | None = None


@dataclass
class Script:
    """Lines to say in turn, then `after`."""

    id: str
    speakers: tuple[Id, ...]
    lines: deque[tuple[Id, str]]
    after: Callable[[], None]
    next_at: datetime
    conversation: Conversation | None = None
    """The conversation the lines are in, when it's one B3 should reflect on."""
    drafted: Line | None = None


class Cafe:
    """The Daily Grind: its barista's shifts, the queue and every order. Tick it on the sim loop.

    The barista is whoever works at the café, else whoever lives there. Without one it's just a
    room with tables."""

    def __init__(
        self,
        clock: Clock,
        bus: EventBus,
        behaviour: Behaviour,
        store: Store,
        llm: Callable[[], LLMClient | None],
        *,
        engine: Callable[[], Engine | None] = lambda: None,
        players: Callable[[], Players | None] = lambda: None,
        director: Callable[[], Any] = lambda: None,
        connected: Callable[[], bool] = lambda: False,
        line_ids: Iterator[int] | None = None,
        menu: Menu | None = None,
        lines: Lines | None = None,
        config: CafeConfig = DEFAULT_CONFIG,
        seed: int | None = None,
    ) -> None:
        self.clock = clock
        self.bus = bus
        self.behaviour = behaviour
        self.movement = behaviour.movement
        self.store = store
        self.llm = llm
        self.engine = engine
        self.players = players
        self.director = director
        self.connected = connected
        self.line_ids = line_ids or itertools.count(1)
        self.menu = menu or load_menu()
        self.lines = lines or Lines()
        self.config = config
        self.rng = random.Random(seed)
        self.barista = barista(behaviour.npcs.values(), config.home)
        town = self.movement.town
        home = town.location(config.home)
        self.map = home.map
        self.maps = {home.map, *(floor.map for floor in home.floors)}
        """Its own and every floor of its building."""
        self.layout = config.layouts[self.map]
        staff = town.location(config.staff)
        self.till = MapTile(map=staff.map, x=staff.entry.x, y=staff.entry.y)
        self.spots = self._queue(town.location(config.queue))
        self.on_shift = False
        self.closing: datetime | None = None
        """When the barista's shift ends, while they're on it."""
        self.visits: dict[Id, Visit] = {}
        self.queue: list[Id] = []
        self.seen: dict[Id, datetime] = {}
        """The goal each resident had when the café last took them in, by when it started."""
        self.served: dict[Id, datetime] = {}
        self.job: Job | None = None
        self.player_job: Job | None = None
        self.greeted = False
        self.script: Script | None = None
        self.going_home: timedelta | None = None
        self.quieted: set[Id] = set()
        """Who the café put in B1's `leave_player_alone`, so B5 doesn't have them greet."""
        self.working = Goal(Activity.COFFEE_SHOP, config.home)

    @property
    def open(self) -> bool:
        """During the barista's shift if they work here, otherwise the café's own hours."""
        if shifts := self._shifts():
            return any(shift.covers(self.clock.now) for shift in shifts)
        return self.config.opens <= self.clock.time_of_day < self.config.closes

    @property
    def serving(self) -> bool:
        """Whether the barista is taking new customers."""
        return self.on_shift and self.open

    def supply(self, goal: Goal, need: Need) -> float:
        """B1's supply hook: the café feeds people only while the barista is on shift."""
        return 0.0 if goal == self.working and need is Need.HUNGER and not self.on_shift else 1.0

    def tick(self, dt: float) -> None:
        now = self.clock.now
        self._shift()
        self._home()
        self._admit(now)
        self._line_up(now)
        self._serve(now)
        self._player(now)
        self._play(now)
        self._sit_down()

    async def write(self, cue: Cue, lines: Sequence[Line]) -> str | None:
        """B5's writer for the barista: at the counter they greet the player and take their
        order, with one structured call. Anything else is left to B5."""
        barista = self.barista
        if barista is None or not self.on_shift or not self._player_at_counter():
            return None
        if cue is Cue.OPEN and self.player_job is None:
            self.greeted = True
            return self.lines.pick("player_greet", self.rng)
        llm = self.llm()
        if cue is not Cue.REPLY or self.player_job is not None or llm is None:
            return None
        npc = self.behaviour.npcs[barista]
        names = {barista: first_name(npc), PLAYER_ID: "Visitor"}
        try:
            order = await llm.structured(
                order_prompt(npc, lines, names, self._feelings(barista, PLAYER_ID)),
                Order,
                system=barista_system(npc, self.menu),
                model=self.config.model,
                purpose="cafe-order",
                priority=1,
            )
        except (StructuredOutputError, LLMError) as error:
            logger.warning("Couldn't take the player's order: %s", error)
            return None
        if order.drink:
            self._take_player_order(order)
        return order.says

    def _shift(self) -> None:
        """A barista who works here comes to the till when B1 sends them to work, late or not
        at all as their shifts go, otherwise at opening time. They stay until their shift ends
        and the queue is served."""
        barista = self.barista
        if barista is None:
            return
        mind = self.behaviour.minds[barista]
        if not self.on_shift and (closing := self._called(barista)) is not None:
            self.on_shift, self.going_home, self.closing = True, None, closing
            self._quiet(barista)
            self.behaviour.hold(barista, self.till, self.working)
            self._log("%s starts their shift", barista)
        elif self.on_shift and not mind.held and not mind.paused:
            self._log("%s is called away from the till", barista)
            self._shut()
        elif (
            self.on_shift
            and self.closing is not None
            and self.clock.now >= self.closing
            and not (self.job or self.player_job or self.queue)
        ):
            self.on_shift, self.closing = False, None
            self._unquiet(barista)
            self.behaviour.release(barista)
            self._log("%s finishes their shift", barista)

    def _called(self, barista: Id) -> datetime | None:
        """When the shift they're due at ends, if it's time they were at the till."""
        if not self._shifts():
            if not self.open:
                return None
            midnight = self.clock.now.replace(hour=0, minute=0, second=0, microsecond=0)
            return midnight + timedelta(hours=self.config.closes)
        mind = self.behaviour.minds[barista]
        if mind.goal != Goal(Activity.WORK, self.config.home) or mind.shift is None:
            return None
        return mind.shift.end

    def _shifts(self) -> list[Shift]:
        """The barista's shifts, if they work here."""
        npc = self.behaviour.npcs[self.barista] if self.barista is not None else None
        return npc.shifts if npc is not None and npc.workplace == self.config.home else []

    def _shut(self) -> None:
        """The barista has gone mid-shift: everyone waiting is let go and their orders dropped."""
        assert self.barista is not None
        self.on_shift, self.closing = False, None
        self._unquiet(self.barista)
        if self.job is not None:
            self._cancel()
        self.player_job = None
        for npc, visit in list(self.visits.items()):
            if visit.phase is not Phase.SITTING:
                self._leave(npc)

    def _home(self) -> None:
        """Off shift, the barista rests and sleeps upstairs, not in front of the counter."""
        barista = self.barista
        if barista is None or self.on_shift:
            return
        mind = self.behaviour.minds[barista]
        if self.going_home is not None:
            if mind.held and mind.walk is None and not mind.paused:
                self.behaviour.release(barista, stay=self.going_home)
                self.going_home = None
            elif not mind.held:
                self.going_home = None
            return
        if mind.paused or mind.held or mind.walk is not None or mind.until is None:
            return
        upstairs = self.layout.upstairs
        here = self.movement.position(barista)
        at_home = mind.goal.activity in AWAY and mind.goal.target == self.config.home
        if at_home and not _at(here, upstairs):
            self.going_home = max(mind.until - self.clock.now, timedelta())
            self.behaviour.hold(barista, upstairs, mind.goal)

    def _admit(self, now: datetime) -> None:
        """Take in residents who've chosen the café: customers queue, everyone else sits."""
        for npc, mind in self.behaviour.minds.items():
            if npc == self.barista or mind.paused:
                continue
            visit = self.visits.get(npc)
            if visit is not None:
                if not mind.held:
                    self._drop(npc)
                elif visit.phase is Phase.COMING and self._inside(npc):
                    self._arrive(visit, now)
                elif visit.phase is Phase.COMING and mind.walk is None:
                    self._log("%s didn't make it to the café", npc)
                    self._leave(npc)
                continue
            goal = mind.goal
            if mind.held or goal.target != self.config.home or goal.activity not in VISITS:
                continue
            fresh = mind.walk is not None or now - mind.since < FRESH
            if self.seen.get(npc) == mind.since or not (fresh or self._inside(npc)):
                continue
            last = self.served.get(npc)
            customer = goal.activity is Activity.COFFEE_SHOP and (
                last is None or now - last >= timedelta(minutes=self.config.again)
            )
            self.seen[npc] = mind.since
            if customer and fresh and self.serving:
                self.visits[npc] = visit = Visit(npc, goal, Phase.COMING)
                if self._inside(npc):
                    self._arrive(visit, now)
                else:
                    self.behaviour.hold(npc, self.layout.entrance, goal)
            elif mind.walk is None and mind.until is not None:
                self._seat(Visit(npc, goal, Phase.SITTING), max(mind.until - now, timedelta()))
            else:
                dwell = self.behaviour.config.dwell.get(goal.activity, self.config.stay)
                self._seat(Visit(npc, goal, Phase.SITTING), self._minutes(dwell))

    def _arrive(self, visit: Visit, now: datetime) -> None:
        if self.serving:
            visit.phase, visit.queued = Phase.QUEUING, now
            self._quiet(visit.npc)
            self.queue.append(visit.npc)
            self._log("%s joins the queue (%d)", visit.npc, len(self.queue))
        else:
            self._seat(visit, self._minutes(self.config.stay))

    def _line_up(self, now: datetime) -> None:
        for n, npc in enumerate(self.queue):
            visit = self.visits[npc]
            spot = self.spots[min(n, len(self.spots) - 1)]
            if visit.spot != spot:
                visit.spot = spot
                self.behaviour.hold(npc, spot, visit.goal)
        for npc in self.queue:
            visit = self.visits[npc]
            assert visit.queued is not None
            ordering = self.job is not None and self.job.customer == npc
            if not ordering and (now - visit.queued).total_seconds() > self.config.patience:
                self._give_up(npc, now)
                return

    def _give_up(self, npc: Id, now: datetime) -> None:
        visit = self.visits[npc]
        assert self.barista is not None and visit.queued is not None
        npcs = self.behaviour.npcs
        self._say(npc, self.lines.pick("give_up", self.rng))
        found, memories = events.gave_up(npcs[self.barista], npcs[npc], self.config, now)
        events.record(self.store, npcs, found, memories, now)
        waited = (now - visit.queued).total_seconds()
        self.bus.publish(GaveUp(npc, self.barista, waited))
        self.served[npc] = now
        self._leave(npc)

    def _serve(self, now: datetime) -> None:
        barista = self.barista
        if barista is None or not self.on_shift:
            return
        job = self.job
        if job is None:
            self._next_customer(now)
            return
        if job.step is Step.ASKING and job.writing is not None and job.writing.done():
            self._written(job)
        elif job.step is Step.MAKING and job.ready_at is not None and now >= job.ready_at:
            job.step = Step.HANDING
            self.behaviour.hold(barista, self.layout.hand_over, self.working)
        elif job.step is Step.HANDING and self.script is None and self._settled(barista):
            self._hand_over(job, now)

    def _next_customer(self, now: datetime) -> None:
        barista = self.barista
        assert barista is not None
        if not self.queue or self._paused(barista):
            return
        npc = self.queue[0]
        visit = self.visits[npc]
        if visit.spot != self.spots[0] or not self._settled(npc) or not self._settled(barista):
            return
        if not _at(self.movement.position(barista), self.till):
            return
        assert visit.queued is not None
        customer = self.behaviour.npcs[npc]
        usual = self.menu.usual(customer)
        drink = self.menu.choose(customer, self.rng, self.config.usual)
        visit.phase = Phase.ORDERING
        job = self.job = Job(npc, drink.name, drink.id, Step.TALKING, visit.queued)
        if self._worth_a_scene(npc):
            llm = self.llm()
            assert llm is not None
            job.step = Step.ASKING
            job.writing = asyncio.get_running_loop().create_task(
                self._exchange(llm, customer, usual)
            )
            self._log("%s orders from %s, written by the LLM", npc, barista)
        else:
            self._run(self._stock_order(customer, drink, usual), lambda: self._make(job))
            self._log("%s orders %s from %s", npc, drink.name, barista)

    async def _exchange(self, llm: LLMClient, customer: Npc, usual: Drink) -> Exchange | None:
        assert self.barista is not None
        barista = self.behaviour.npcs[self.barista]
        feelings = {
            barista.id: self._feelings(barista.id, customer.id),
            customer.id: self._feelings(customer.id, barista.id),
        }
        try:
            async with asyncio.timeout(SCENE_TIMEOUT):
                return await llm.structured(
                    exchange_prompt(barista, customer, feelings, usual, self.menu, self.clock.now),
                    Exchange,
                    system=EXCHANGE_SYSTEM,
                    model=self.config.model,
                    purpose="cafe-exchange",
                )
        except (StructuredOutputError, LLMError, TimeoutError) as error:
            logger.warning("Couldn't write %s's order: %r", customer.id, error)
            return None

    def _written(self, job: Job) -> None:
        assert self.barista is not None and job.writing is not None
        task, job.writing = job.writing, None
        exchange = None if task.cancelled() else task.result()
        customer = self.behaviour.npcs[job.customer]
        job.step = Step.TALKING
        if exchange is None:
            drink = self.menu.get(job.menu) or self.menu.usual(customer)
            script = self._stock_order(customer, drink, self.menu.usual(customer))
            self._run(script, lambda: self._make(job))
            return
        job.drink, job.menu = (
            _plain(exchange.drink),
            exchange.menu if self.menu.get(exchange.menu) else None,
        )
        speakers = {"barista": self.barista, "customer": job.customer}
        said = [(speakers[line.by], line.text) for line in exchange.lines if line.text.strip()]
        self._run(said, lambda: self._make(job), scene=True)

    def _stock_order(self, customer: Npc, drink: Drink, usual: Drink) -> list[tuple[Id, str]]:
        assert self.barista is not None
        barista, names = self.barista, self._names(customer.id, drink.name)
        familiar = self._feelings(barista, customer.id).familiarity >= self.config.regular
        if familiar and drink == usual:
            return [
                (barista, self.lines.pick("greet_regular", self.rng, **names)),
                (customer.id, self.lines.pick("usual", self.rng, **names)),
            ]
        return [
            (barista, self.lines.pick("greet", self.rng, **names)),
            (customer.id, self.lines.pick("order", self.rng, **names)),
            (barista, self.lines.pick("confirm", self.rng, **names)),
        ]

    def _make(self, job: Job) -> None:
        barista = self.barista
        assert barista is not None
        self.behaviour.hold(barista, self.layout.machine, self.working)
        job.step = Step.MAKING
        job.ready_at = self.clock.now + timedelta(seconds=self.menu.seconds(job.menu))
        if job.customer == PLAYER_ID:
            return
        if job.customer in self.queue:
            self.queue.remove(job.customer)
            visit = self.visits[job.customer]
            visit.phase, visit.spot = Phase.WAITING, self.layout.pickup
            self.behaviour.hold(job.customer, visit.spot, visit.goal)
            self.bus.publish(Ordered(job.customer, barista, job.drink, job.menu))

    def _hand_over(self, job: Job, now: datetime) -> None:
        barista = self.barista
        assert barista is not None
        names = self._names(job.customer, job.drink)
        if not job.wrong and len(self.menu.drinks) > 1 and self.rng.random() < self.config.mistake:
            job.wrong = True
            other = self.rng.choice([d for d in self.menu.drinks if d.name != job.drink])
            script = [
                (barista, self.lines.pick("ready", self.rng, **(names | {"drink": other.name}))),
                (job.customer, self.lines.pick("wrong", self.rng, **names)),
                (barista, self.lines.pick("sorry", self.rng, **names)),
            ]
            self._log("%s makes %s %s instead of %s", barista, job.customer, other.name, job.drink)
            self._run(script, lambda: self._make(job))
            return
        waited = (now - job.waited_from).total_seconds()
        thanks = "slow" if waited > self.config.slow else "thanks"
        script = [
            (barista, self.lines.pick("ready", self.rng, **names)),
            (job.customer, self.lines.pick(thanks, self.rng, **names)),
        ]
        self._run(script, lambda: self._finish(job))

    def _finish(self, job: Job) -> None:
        barista, now = self.barista, self.clock.now
        assert barista is not None
        npcs = self.behaviour.npcs
        waited = (now - job.waited_from).total_seconds()
        found, memories = events.served(
            npcs[barista], npcs[job.customer], job.drink, waited, job.wrong, self.config, now
        )
        events.record(self.store, npcs, found, memories, now)
        self.bus.publish(Served(job.customer, barista, job.drink, waited, job.wrong))
        self._log("%s serves %s: %s, after %.0fs", barista, job.customer, job.drink, waited)
        self.served[job.customer] = now
        self.job = None
        self.behaviour.hold(barista, self.till, self.working)
        visit = self.visits.get(job.customer)
        if visit is None:
            return
        if self.rng.random() < self._sit_chance(npcs[job.customer]):
            self._seat(visit, self._minutes(self.config.stay))
        else:
            self._leave(job.customer)

    def _take_player_order(self, order: Order) -> None:
        menu = order.menu if self.menu.get(order.menu) else None
        assert order.drink is not None and self.barista is not None
        now, drink = self.clock.now, _plain(order.drink)
        ready = now + timedelta(seconds=self.menu.seconds(menu))
        self.player_job = Job(PLAYER_ID, drink, menu, Step.MAKING, now, ready)
        self.bus.publish(Ordered(PLAYER_ID, self.barista, drink, menu))
        self._log("The player orders %s from %s", drink, self.barista)

    def _player(self, now: datetime) -> None:
        barista = self.barista
        if barista is None or not self.on_shift:
            return
        if not self._player_at_counter():
            self.greeted = False
        elif not self.greeted and self.player_job is None and self._barista_free_for_player():
            players = self.players()
            text = self.lines.pick("player_greet", self.rng)
            if players is not None and players.interject(barista, text):
                self.greeted = True
        job = self.player_job
        if job is None or job.ready_at is None or now < job.ready_at:
            return
        drink = job.drink
        players = self.players()
        near = self._from_player(barista)
        text = self.lines.pick("player_ready", self.rng, drink=drink)
        reach = DEFAULT_PLAYER_CONFIG.say_range
        handed = near is not None and near <= reach and players is not None
        if not (handed and players.interject(barista, text)):
            self._say(barista, self.lines.pick("player_gone", self.rng, drink=drink))
        waited = (now - job.waited_from).total_seconds()
        self.bus.publish(Served(PLAYER_ID, barista, drink, waited, False))
        self._log("%s serves the player: %s", barista, drink)
        self.player_job = None

    def _barista_free_for_player(self) -> bool:
        assert self.barista is not None
        if self._paused(self.barista) or self.script is not None:
            return False
        return self.job is None or self.job.step is Step.MAKING

    def _worth_a_scene(self, customer: Id) -> bool:
        """Whether the ambient director would want a conversation near the player now, so an
        order can be one, written by the LLM, rather than stock lines."""
        director, engine, barista = self.director(), self.engine(), self.barista
        if director is None or engine is None or barista is None or self.llm() is None:
            return False
        config, now = director.config, self.clock.now
        if not config.enabled or not self.connected() or engine.talking(PLAYER_ID):
            return False
        near = [d for npc in (barista, customer) if (d := self._from_player(npc)) is not None]
        if not near or min(near) > config.earshot or director.earshot.heard:
            return False
        if now - director.heard_at < timedelta(seconds=config.quiet):
            return False
        if now - director.nudged_at < timedelta(seconds=config.retry):
            return False
        keen = min(engine.accept_score(customer, barista), engine.accept_score(barista, customer))
        return keen > config.accept_bar

    def _seat(self, visit: Visit, stay: timedelta) -> None:
        seat = self._free_seat()
        if seat is None:
            self.visits.pop(visit.npc, None)
            self._unquiet(visit.npc)
            if self.behaviour.minds[visit.npc].held:
                self.behaviour.release(visit.npc, stay=stay)
            return
        visit.phase, visit.seat, visit.stay = Phase.SITTING, seat, stay
        self._unquiet(visit.npc)
        visit.spot = seat
        self.visits[visit.npc] = visit
        self.behaviour.hold(visit.npc, visit.spot, visit.goal)

    def _sit_down(self) -> None:
        for npc, visit in list(self.visits.items()):
            if visit.phase is Phase.SITTING and self._settled(npc):
                del self.visits[npc]
                self.behaviour.release(npc, stay=visit.stay)

    def _leave(self, npc: Id) -> None:
        self.visits.pop(npc, None)
        self._unquiet(npc)
        if npc in self.queue:
            self.queue.remove(npc)
        self.behaviour.release(npc)

    def _drop(self, npc: Id) -> None:
        """Someone else let go of them, as restoring a save or an urgent need does. Their order
        goes with them."""
        self.visits.pop(npc, None)
        self._unquiet(npc)
        if npc in self.queue:
            self.queue.remove(npc)
        if self.job is not None and self.job.customer == npc:
            self._cancel()

    def _cancel(self) -> None:
        """Drop the order in hand, mid-word or mid-drink, and go back to the till."""
        job, self.job = self.job, None
        assert job is not None
        if job.writing is not None:
            job.writing.cancel()
        script = self.script
        if script is not None and job.customer in script.speakers:
            self.script = None
            if script.conversation is not None:
                script.conversation.ended = self.clock.now
                self.bus.publish(ConversationEnded(script.conversation.model_copy(deep=True)))
        self._log("%s's order is dropped", job.customer)
        if self.on_shift and self.barista is not None:
            self.behaviour.hold(self.barista, self.till, self.working)

    def _quiet(self, npc: Id) -> None:
        if npc not in self.behaviour.leave_player_alone:
            self.behaviour.leave_player_alone.add(npc)
            self.quieted.add(npc)

    def _unquiet(self, npc: Id) -> None:
        if npc in self.quieted:
            self.quieted.discard(npc)
            self.behaviour.leave_player_alone.discard(npc)

    def _run(
        self, lines: Sequence[tuple[Id, str]], after: Callable[[], None], *, scene: bool = False
    ) -> None:
        now = self.clock.now
        speakers = sorted({speaker for speaker, _ in lines})
        id = f"{now:%Y%m%dT%H%M%S}-cafe-{'-'.join(speakers)}"
        conversation = None
        if scene:
            conversation = Conversation(id=id, participants=speakers, started=now)
            self.bus.publish(ConversationStarted(conversation.model_copy(deep=True)))
        self.script = Script(id, tuple(speakers), deque(lines), after, now, conversation)
        if conversation is not None:
            self._draft(self.script)

    def _play(self, now: datetime) -> None:
        script = self.script
        if script is None or now < script.next_at:
            return
        if any(self._paused(speaker) for speaker in script.speakers):
            return
        engine = self.engine()
        if script.conversation is not None and engine is not None:
            ends = engine.still_playing(script.conversation)
            if ends is not None and ends > now:
                script.next_at = ends
                return
        if not script.lines:
            self.script = None
            if script.conversation is not None:
                script.conversation.ended = now
                self.bus.publish(ConversationEnded(script.conversation.model_copy(deep=True)))
            script.after()
            return
        speaker, text = script.lines.popleft()
        line = script.drafted or self._line(script.id, speaker, text)
        line = line.model_copy(update={"timestamp": now})
        if script.conversation is not None:
            if engine is not None:
                line = engine.as_voiced(line)
            script.conversation.lines.append(line)
        self.bus.publish(LineSpoken(line))
        script.next_at = line.timestamp + timedelta(seconds=line.duration + self.config.turn_gap)
        script.drafted = None
        if script.conversation is not None:
            self._draft(script)

    def _draft(self, script: Script) -> None:
        if script.lines:
            speaker, text = script.lines[0]
            script.drafted = self._line(script.id, speaker, text, at=script.next_at)
            self.bus.publish(LineDrafted(script.drafted))

    def _say(self, speaker: Id, text: str) -> None:
        """A line on its own, outside any conversation, so nothing reflects on it."""
        now = self.clock.now
        self.bus.publish(
            LineSpoken(self._line(f"{now:%Y%m%dT%H%M%S}-cafe-{speaker}", speaker, text))
        )

    def _line(
        self, conversation: str, speaker: Id, text: str, *, at: datetime | None = None
    ) -> Line:
        return Line(
            id=next(self.line_ids),
            conversation_id=conversation,
            speaker=speaker,
            text=text,
            timestamp=at or self.clock.now,
            duration=round(duration(text, rate=speaking_rate(speaker)), 2),
        )

    def _names(self, customer: Id, drink: str) -> dict[str, str]:
        assert self.barista is not None
        npcs = self.behaviour.npcs
        who = first_name(npcs[customer]) if customer in npcs else "Visitor"
        return {"customer": who, "barista": first_name(npcs[self.barista]), "drink": drink}

    def _feelings(self, owner: Id, about: Id) -> Relationship:
        stored = self.store.relationship(owner, about)
        now = self.clock.now
        return as_of(stored, now) if stored else meet(self.behaviour.npcs[owner], about)

    def _sit_chance(self, npc: Npc) -> float:
        weights = self.config.sit_values
        chance = self.config.sit + sum(w * (npc.values[v] - 0.5) for v, w in weights.items())
        return min(max(chance, 0.0), 1.0)

    def _free_seat(self) -> MapTile | None:
        taken = {(p.map, round(p.x), round(p.y)) for p in self.movement.entities().values()}
        taken |= {(v.seat.map, v.seat.x, v.seat.y) for v in self.visits.values() if v.seat}
        free = [seat for seat in self.layout.seats if (seat.map, seat.x, seat.y) not in taken]
        return self.rng.choice(free) if free else None

    def _player_at_counter(self) -> bool:
        try:
            here = self.movement.position(PLAYER_ID)
        except KeyError:
            return False
        stand = self.spots[0]
        return here.map == stand.map and math.dist(here, (stand.x, stand.y)) <= 1.0

    def _from_player(self, npc: Id) -> float | None:
        try:
            return between(self.movement, npc, PLAYER_ID)
        except KeyError:
            return None

    def _inside(self, npc: Id) -> bool:
        return self.movement.position(npc).map in self.maps

    def _settled(self, npc: Id) -> bool:
        mind = self.behaviour.minds[npc]
        return mind.walk is None and not mind.paused

    def _paused(self, npc: Id) -> bool:
        mind = self.behaviour.minds.get(npc)
        return mind is not None and mind.paused

    def _queue(self, lane: Location) -> list[MapTile]:
        """The front of the queue at the lane's entry, then each tile to stand on behind it: down
        the grid, or on a side-view map along the floor and through the lane."""
        town, front = self.movement.maps[lane.map], lane.entry
        dx, dy = (1 if front.x == lane.area.x else -1, 0) if town.side_view else (0, 1)
        spots = [MapTile(map=lane.map, x=front.x, y=front.y)]
        x, y = front.x + dx, front.y + dy
        while town.standing(x, y):
            spots.append(MapTile(map=lane.map, x=x, y=y))
            x, y = x + dx, y + dy
        return spots

    def _minutes(self, bounds: tuple[float, float]) -> timedelta:
        return timedelta(minutes=self.rng.uniform(*bounds))

    def _log(self, message: str, *args: object) -> None:
        logger.info(f"%s  {message}", self.clock, *args)


def _plain(drink: str) -> str:
    """A drink as said mid-sentence: "Espresso" becomes "espresso"."""
    drink = drink.strip()
    return drink[:1].lower() + drink[1:] if drink[1:2].islower() else drink


def _at(point: Point, tile: MapTile) -> bool:
    return point.map == tile.map and math.dist(point, (tile.x, tile.y)) < 0.5


def cafe_of(app: Starlette) -> Cafe:
    """The server's café on `app.state.cafe`, created on first use."""
    if not hasattr(app.state, "cafe"):
        from simile.behaviour import behaviour_of
        from simile.conversation.engine import line_ids
        from simile.memory import memory_of
        from simile.protocol import hub_of
        from simile.sim import world_of

        world, hub = world_of(app), hub_of(app)
        behaviour = behaviour_of(app)
        app.state.cafe = Cafe(
            world.clock,
            world.bus,
            behaviour,
            memory_of(app),
            lambda: getattr(app.state, "llm", None),
            engine=lambda: getattr(app.state, "conversation", None),
            players=lambda: getattr(app.state, "players", None),
            director=lambda: getattr(app.state, "ambient", None),
            connected=lambda: bool(hub.connections),
            line_ids=line_ids(app),
        )
        # As random as behaviour is, so a seeded village plays out the same every time.
        app.state.cafe.rng.setstate(behaviour.rng.getstate())
    return app.state.cafe
