import logging
import math
import random
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Protocol

from pydantic import JsonValue
from starlette.applications import Starlette

from simile.behaviour.config import DEFAULT_CONFIG, Activity, BehaviourConfig, Need
from simile.behaviour.events import GoalChosen
from simile.behaviour.inspiration import inspiration
from simile.behaviour.scoring import (
    UNPLACED,
    Goal,
    MuralSpot,
    Other,
    Places,
    Situation,
    Supply,
    Work,
    affinity,
    asleep,
    bedtime,
    best_per_activity,
    choose,
    finances,
    plenty,
    punctuality,
    savings,
    scores,
    skip_chance,
    wake,
)
from simile.schema import (
    PLAYER_ID,
    Conversation,
    Id,
    LocationKind,
    MapTile,
    Medium,
    Memory,
    Npc,
    PayKind,
    Relationship,
    Tile,
    Traits,
    Weekday,
)
from simile.sim import Clock, EventBus
from simile.social import as_of, cast_traits, meet, trait_factor
from simile.world.movement import Movement, Outcome, Point, Target, Walk

logger = logging.getLogger(__name__)

type ConversationRequest = Callable[[Id, Id], bool]
type NewsReader = Callable[[Npc], None]
type NewsInterest = Callable[[Npc], float]
type LiveConversations = Callable[[], list[Conversation]]
type WorkMaker = Callable[[Npc, Id | None], None]
type WallPicker = Callable[[Npc], MuralSpot | None]
type Purse = Callable[[Npc], float | None]
type Pricing = Callable[[Npc, Goal], float]

NEUTRAL = Traits()
AT_HOME = (Activity.HOME, Activity.SLEEP)
GOING_TO_A_PLACE = (
    Activity.HOME,
    Activity.SLEEP,
    Activity.COFFEE_SHOP,
    Activity.SQUARE,
    Activity.NEWS,
    Activity.PARK,
    Activity.NOODLE_BAR,
    Activity.MAKER_SPACE,
    Activity.GALLERY,
    Activity.CREATE,
    Activity.WORK,
)
HOUR = timedelta(hours=1)
RESUMED = (Activity.CREATE, Activity.WORK)
"""What they go back to after a talk."""


def decline(a: Id, b: Id) -> bool:
    return False


def skip_news(npc: Npc) -> None:
    return None


def no_news(npc: Npc) -> float:
    return 0.0


def no_conversations() -> list[Conversation]:
    return []


def make_nothing(npc: Npc, wall: Id | None) -> None:
    return None


def no_wall(npc: Npc) -> MuralSpot | None:
    return None


def no_money(npc: Npc) -> float | None:
    return None


def nothing(npc: Npc, goal: Goal) -> float:
    return 0.0


class Hooks:
    """The interfaces other modules implement, stubbed until they do. See the README."""

    def __init__(self) -> None:
        self.request_conversation: ConversationRequest = decline
        self.read_news: NewsReader = skip_news
        self.news_interest: NewsInterest = no_news
        self.conversations: LiveConversations = no_conversations
        self.create: WorkMaker = make_nothing
        self.mural_wall: WallPicker = no_wall
        self.supply: Supply = plenty
        self.money: Purse = no_money
        self.price: Pricing = nothing
        self.earnings: Pricing = nothing

    def set(
        self,
        *,
        request_conversation: ConversationRequest | None = None,
        read_news: NewsReader | None = None,
        news_interest: NewsInterest | None = None,
        conversations: LiveConversations | None = None,
        create: WorkMaker | None = None,
        mural_wall: WallPicker | None = None,
        supply: Supply | None = None,
        money: Purse | None = None,
        price: Pricing | None = None,
        earnings: Pricing | None = None,
    ) -> Callable[[], None]:
        """Plug in the hooks given and return a function that puts back what they replaced."""
        given = {
            "request_conversation": request_conversation,
            "read_news": read_news,
            "news_interest": news_interest,
            "conversations": conversations,
            "create": create,
            "mural_wall": mural_wall,
            "supply": supply,
            "money": money,
            "price": price,
            "earnings": earnings,
        }
        hooks = {name: hook for name, hook in given.items() if hook is not None}
        previous = {name: getattr(self, name) for name in hooks}
        for name, hook in hooks.items():
            setattr(self, name, hook)

        def restore() -> None:
            for name, hook in previous.items():
                setattr(self, name, hook)

        return restore


class Relationships(Protocol):
    def relationships(self, owner: str) -> list[Relationship]: ...


@dataclass
class Due:
    """A shift they're due at: when it runs, when they'll set off for it and whether they'll
    skip it."""

    start: datetime
    end: datetime
    set_off: datetime
    skipping: bool
    called: bool = False
    """Whether they've been sent off to it."""


@dataclass
class Mind:
    npc: Npc
    needs: dict[Need, float]
    bedtime: float
    wake: float
    goal: Goal
    since: datetime
    until: datetime | None = None
    """When the NPC will next decide. None while walking or paused."""
    walk: Walk | None = None
    paused: bool = False
    chases: int = 0
    options: dict[str, float] = field(default_factory=dict)
    """The best score of each activity at the last decision."""
    cooldowns: dict[Id, datetime] = field(default_factory=dict)
    nudge: tuple[Goal, float] | None = None
    """A goal and the bonus it gets at the next decision."""
    finishes: bool = False
    """Whether they're staying at their goal until `until`, so leaving then finishes it."""
    mural: MuralSpot | None = None
    """The wall a muralist would paint at the last decision."""
    interrupted: tuple[Goal, timedelta] | None = None
    """What they were making when a talk paused them, and how long it had left."""
    held: tuple[Target, Goal] | None = None
    """Where another module keeps them, and with what goal, until it lets go."""
    pressed: frozenset[Need] = frozenset()
    """The needs above their critical level that they've already acted on."""
    eating: dict[Need, datetime] = field(default_factory=dict)
    """Needs their place has started meeting, by the stay's `since`. One with an appetite starts
    only once it's that high."""
    shift: Due | None = None
    """Their current or next shift."""
    staying_on: datetime | None = None
    """Until when they can stay on at work after their last shift."""
    skipping: tuple[date, bool] | None = None
    """The last working day they decided whether to skip, and what they decided."""
    inspired: list[tuple[datetime, float]] = field(default_factory=list)
    """What new memories added to their inspiration in the last sim hour, and when."""


class Behaviour:
    """Every NPC's needs and goals. Tick it on the sim loop."""

    def __init__(
        self,
        clock: Clock,
        bus: EventBus,
        movement: Movement,
        npcs: Iterable[Npc],
        relationships: Relationships | None = None,
        *,
        config: BehaviourConfig = DEFAULT_CONFIG,
        seed: int | None = None,
        traits: Mapping[Id, Traits] | None = None,
    ) -> None:
        self.clock = clock
        self.bus = bus
        self.movement = movement
        self.npcs = {npc.id: npc for npc in npcs}
        self.relationships = relationships
        self.traits = dict(traits or {})
        self.config = config
        self.rng = random.Random(seed)
        self.hooks = Hooks()
        self.leave_player_alone: set[Id] = set()
        self.places = Places(movement.town)
        self.minds: dict[Id, Mind] = {}
        self._finished: list[Walk] = []
        self._elapsed = 0.0
        self._needs_at = clock.now

    def start(self) -> None:
        """Put every NPC who isn't on the map yet at home, and give them their first goal."""
        now = self.clock.now
        placed = self.movement.entities()
        self._needs_at = now
        for npc in self.npcs.values():
            if npc.id not in placed:
                self.movement.place(npc.id, npc.home)
            needs = {
                need: self.rng.uniform(*self.config.start_needs[need])
                if npc.craft or need is not Need.INSPIRATION
                else 0.0
                for need in Need
                if need is not Need.FINANCES
            }
            needs[Need.FINANCES] = self._finances(npc)
            mind = Mind(
                npc,
                needs,
                bedtime(npc.values, self.config),
                wake(npc.values, self.config),
                Goal(Activity.IDLE),
                now,
            )
            if self._at_home(mind):
                mind.goal = Goal(Activity.HOME, npc.home)
            self.minds[npc.id] = mind
        for mind in self.minds.values():
            self._plan(mind)
        keen = self._keenest()
        for mind in self.minds.values():
            if self._asleep(mind):
                self._sleep(mind)
            elif mind.npc.id in keen:
                self._head_start(mind, keen[mind.npc.id])
            elif mind.goal.activity is Activity.HOME:
                self._publish(mind)
                mind.until = now + self._minutes(self.config.start_dwell)
            else:
                self._decide(mind)

    def _keenest(self) -> dict[Id, timedelta]:
        """The `head_starts` residents keenest to make something who could be making it at home
        now, with how long their stay has left: awake, at home and not off to work before it ends.
        Muralists need a wall, so they're left out."""
        now, keen = self.clock.now, {}
        ready = [
            mind
            for mind in self.minds.values()
            if mind.npc.craft is not None
            and not _paints(mind.npc)
            and mind.goal.activity is Activity.HOME
            and not self._asleep(mind)
        ]
        ready.sort(key=lambda mind: -mind.needs[Need.INSPIRATION])
        for mind in ready:
            if len(keen) >= self.config.head_starts:
                break
            left = self._minutes(self.config.head_start)
            if mind.shift is None or mind.shift.set_off > now + left:
                keen[mind.npc.id] = left
        return keen

    def _head_start(self, mind: Mind, left: timedelta) -> None:
        now = self.clock.now
        mind.goal, mind.since, mind.until = Goal(Activity.CREATE, mind.npc.home), now, now + left
        mind.finishes = True
        self._publish(mind)

    def inspire(self, memory: Memory) -> float:
        """Raise a crafter's inspiration for a new memory, up to `inspiration_hourly` a sim hour,
        and return by how much. The memory store's listener."""
        mind = self.minds.get(memory.owner)
        if mind is None:
            return 0.0
        now = self.clock.now
        mind.inspired = [(at, n) for at, n in mind.inspired if now - at < HOUR]
        room = self.config.inspiration_hourly - sum(n for _, n in mind.inspired)
        bump = min(inspiration(memory, mind.npc, self.config), room)
        if bump <= 0:
            return 0.0
        mind.needs[Need.INSPIRATION] = _clamp(mind.needs[Need.INSPIRATION] + bump)
        mind.inspired.append((now, bump))
        return bump

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed >= self.config.think_every - 1e-9:
            self._elapsed = 0.0
            self._think()
        while self._finished:
            self._settle(self._finished.pop(0))

    def pause(self, npc: Id, talking_to: Id | None = None) -> None:
        """Stop the NPC where they are and make no decisions for them until `resume`. Does
        nothing for the player."""
        if npc == PLAYER_ID:
            return
        mind = self.minds[npc]
        if mind.finishes and mind.goal.activity in RESUMED and mind.until is not None:
            mind.interrupted = (mind.goal, mind.until - self.clock.now)
        mind.paused, mind.finishes = True, False
        mind.until, mind.nudge = None, None
        walk, mind.walk = mind.walk, None
        if walk is not None:
            self.movement.stop(npc)
        if mind.goal != Goal(Activity.TALK, talking_to):
            mind.goal, mind.since = Goal(Activity.TALK, talking_to), self.clock.now
            self._publish(mind)

    def resume(self, npc: Id) -> None:
        """Let the NPC decide again, on the next tick. Does nothing for the player."""
        if npc == PLAYER_ID:
            return
        mind = self.minds[npc]
        if not mind.paused:
            return
        mind.paused = False
        mind.until = self.clock.now
        if mind.held is not None:
            self._take_up(mind)
        elif mind.interrupted is not None:
            (goal, left), mind.interrupted = mind.interrupted, None
            mind.goal, mind.since, mind.finishes = goal, self.clock.now, True
            mind.until += left
            if goal.activity is Activity.WORK:
                due = self._due(mind)
                mind.until = min(mind.until, due.end) if due else self.clock.now
            self._publish(mind)

    def restore(
        self,
        npc: Id,
        goal: Goal,
        needs: Mapping[Need, float],
        since: datetime,
        until: datetime | None,
        cooldowns: Mapping[Id, datetime],
    ) -> None:
        """Put the NPC back to what they were doing when saved, after the clock has been set:
        their walk stops, and with no `until` (they were walking or talking) they decide again
        on the next think. A stay that's already over is dropped rather than finished, and a shift
        already under way waits until the stay is over. Everyone's needs rise from now."""
        mind = self.minds[npc]
        walk, mind.walk = mind.walk, None
        if walk is not None:
            self.movement.stop(npc)
        mind.goal, mind.since, mind.until = goal, since, until or self.clock.now
        mind.needs.update(needs)
        mind.cooldowns = dict(cooldowns)
        mind.paused, mind.chases, mind.options, mind.nudge = False, 0, {}, None
        mind.finishes = until is not None and until > self.clock.now
        mind.interrupted, mind.held = None, None
        mind.shift, mind.staying_on = None, None
        self._plan(mind)
        if mind.shift is not None and mind.shift.set_off <= self.clock.now:
            mind.shift.called = True
        self._needs_at = self.clock.now
        self._publish(mind)

    def hold(self, npc: Id, target: Target, goal: Goal) -> None:
        """Walk them to `target` and keep them there with `goal`, making no decisions and out of
        seekers' reach, until `release`. A talk pauses the hold, and they go back after it."""
        mind = self.minds[npc]
        mind.held = (target, goal)
        if not mind.paused:
            self._take_up(mind)

    def release(self, npc: Id, stay: timedelta | None = None) -> None:
        """Let go of them. With `stay` they stay put with the held goal for that long, as if just
        arrived; otherwise they decide on the next think."""
        mind = self.minds[npc]
        if mind.held is None:
            return
        mind.held = None
        if mind.paused:
            return
        walk, mind.walk = mind.walk, None
        if walk is not None:
            self.movement.stop(npc)
        mind.until = self.clock.now + (stay or timedelta())
        mind.finishes = stay is not None

    def nudge(self, npc: Id, goal: Goal, bonus: float) -> bool:
        """Add `bonus` to `goal` when they decide, on the next think. False if paused, held or
        asleep."""
        mind = self.minds[npc]
        if mind.paused or mind.held or self._asleep(mind):
            return False
        walk, mind.walk = mind.walk, None
        if walk is not None:
            self.movement.stop(npc)
        mind.nudge, mind.until, mind.finishes = (goal, bonus), self.clock.now, False
        return True

    def available(self, seeker: Id, other: Id) -> bool:
        """Whether `seeker` could seek `other` out: not asleep, at home, talking, recently refused
        or, for the player, left alone."""
        return self._available(self.minds[seeker], other)

    def at_home(self, npc: Id) -> bool:
        """Whether they're at or heading home, to rest, sleep or make something there."""
        return self._home_bound(self.minds[npc])

    def working(self, npc: Id) -> bool:
        """Whether they're at their workplace working: there for work, or kept there by it."""
        mind = self.minds[npc]
        workplace = mind.npc.workplace
        if workplace is None or mind.paused or mind.walk is not None:
            return False
        if mind.held is not None:
            goal = mind.held[1]
            return goal.target == workplace and goal.activity not in AT_HOME
        return mind.goal == Goal(Activity.WORK, workplace)

    def savings(self, npc: Id) -> float:
        """Their savings target, in money."""
        return savings(self.npcs[npc].values, self.config)

    def goal(self, npc: Id) -> Goal:
        return self.minds[npc].goal

    def needs(self, npc: Id) -> dict[Need, float]:
        return dict(self.minds[npc].needs)

    def state(self, npc: Id) -> dict[str, JsonValue]:
        """The NPC's goal, needs and last decision, for the debug overlay."""
        mind = self.minds[npc]
        money = self._call(self.hooks.money, mind.npc)
        shown = (Need.INSPIRATION, Need.FINANCES)
        due = mind.shift
        return {
            "goal": str(mind.goal),
            "activity": mind.goal.activity.value,
            "target": mind.goal.target,
            "walking": mind.walk is not None,
            "paused": mind.paused,
            "since": mind.since.isoformat(),
            "until": mind.until.isoformat() if mind.until else None,
            "needs": {
                need.value: round(value, 3)
                for need, value in mind.needs.items()
                if need not in shown
                or (need is Need.INSPIRATION and mind.npc.craft)
                or (need is Need.FINANCES and isinstance(money, int | float))
            },
            "money": round(money, 2) if isinstance(money, int | float) else None,
            "shift": {
                "start": due.start.isoformat(),
                "end": due.end.isoformat(),
                "skipping": due.skipping,
            }
            if due
            else None,
            "options": dict(mind.options),
            "bedtime": round(mind.bedtime, 2),
            "wake": round(mind.wake, 2),
        }

    def _think(self) -> None:
        now = self.clock.now
        hours = (now - self._needs_at) / timedelta(hours=1)
        self._needs_at = now
        self._update_needs(hours)
        for mind in self.minds.values():
            self._plan(mind)
            if mind.paused:
                continue
            if self._asleep(mind):
                if not mind.held and mind.goal.activity is not Activity.SLEEP:
                    self._sleep(mind)
            elif self._pressing(mind) or self._woken(mind):
                self._interrupt(mind)
            elif mind.held:
                continue
            elif self._setting_off(mind):
                self._interrupt(mind)
            elif mind.walk is None and mind.until is not None and now >= mind.until:
                self._decide(mind)

    def _plan(self, mind: Mind) -> None:
        """Keep their next shift in view, and once one ends, how long a wage earner still at work
        can stay on."""
        npc, now, due = mind.npc, self.clock.now, mind.shift
        if npc.workplace is None or not npc.shifts or (due is not None and now < due.end):
            return
        if due is not None and _wage(npc) and mind.goal == Goal(Activity.WORK, npc.workplace):
            mind.staying_on = due.end + timedelta(hours=self.config.overtime)
        mind.shift = self._next_shift(mind)

    def _next_shift(self, mind: Mind) -> Due:
        npc, now, config = mind.npc, self.clock.now, self.config
        assert npc.workplace is not None
        midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
        start, end = min(
            (day + timedelta(hours=shift.start), day + timedelta(hours=shift.end))
            for day in (midnight + timedelta(days=n) for n in range(8))
            for shift in npc.shifts
            if Weekday.of(day) in shift.days and day + timedelta(hours=shift.end) > now
        )
        walk = self.places.walk_minutes(self._entry(npc.home), self._entry(npc.workplace))
        early = punctuality(npc.values, config)
        early += self.rng.uniform(-config.set_off_jitter, config.set_off_jitter)
        set_off = start - timedelta(minutes=walk + early)
        if mind.skipping is None or mind.skipping[0] != start.date():
            chance = skip_chance(npc.values, mind.needs[Need.FINANCES], config)
            mind.skipping = (start.date(), self.rng.random() < chance)
        return Due(start, end, set_off, mind.skipping[1])

    def _due(self, mind: Mind) -> Due | None:
        """Their shift, from when they set off for it until it ends, unless they're skipping it."""
        due, now = mind.shift, self.clock.now
        if due is None or due.skipping or not due.set_off <= now < due.end:
            return None
        return due

    def _setting_off(self, mind: Mind) -> bool:
        """Whether it's time they dropped what they're doing for a shift, once a shift."""
        due = self._due(mind)
        if due is None or due.called:
            return False
        due.called = True
        return mind.goal != Goal(Activity.WORK, mind.npc.workplace)

    def _work(self, mind: Mind) -> Work | None:
        npc, now = mind.npc, self.clock.now
        if npc.workplace is None:
            return None
        if (due := self._due(mind)) is not None:
            return Work(npc.workplace, True, (due.end - max(now, due.start)) / HOUR)
        here = mind.goal == Goal(Activity.WORK, npc.workplace)
        if here and mind.staying_on is not None and now < mind.staying_on:
            low, high = self.config.dwell.get(Activity.WORK, (0.0, 0.0))
            left = (mind.staying_on - now) / HOUR
            return Work(npc.workplace, False, min((low + high) / 2 / 60, left))
        return None

    def _woken(self, mind: Mind) -> bool:
        """Whether a shift has just got them up before they'd wake."""
        sleeping = mind.goal.activity is Activity.SLEEP and mind.walk is None and not mind.held
        return sleeping and asleep(self.clock.time_of_day, mind.bedtime, mind.wake)

    def _asleep(self, mind: Mind) -> bool:
        """Asleep at this hour, unless a shift has them up: `ready` before they set off, until
        it ends."""
        due, now = mind.shift, self.clock.now
        up = timedelta(minutes=self.config.ready)
        if due is not None and not due.skipping and due.set_off - up <= now < due.end:
            return False
        return asleep(self.clock.time_of_day, mind.bedtime, mind.wake)

    def _entry(self, location: Id) -> Point:
        place = self.places.location(location)
        return Point(place.entry.x, place.entry.y, place.map)

    def _finances(self, npc: Npc) -> float:
        money = self._call(self.hooks.money, npc)
        if not isinstance(money, int | float):
            return 0.0
        return finances(money, savings(npc.values, self.config))

    def _price(self, hook: Pricing, npc: Npc, goal: Goal) -> float:
        price = self._call(hook, npc, goal)
        return float(price) if isinstance(price, int | float) else 0.0

    def _pressing(self, mind: Mind) -> bool:
        """Whether a need has just gone critical that what they're doing doesn't meet."""
        critical = self._critical(mind)
        fresh, mind.pressed = critical - mind.pressed, critical
        return any(not self._meets(mind, need) for need in fresh)

    def _critical(self, mind: Mind) -> frozenset[Need]:
        return frozenset(
            need
            for need, urgency in self.config.urgency.items()
            if urgency.critical is not None and mind.needs[need] >= urgency.critical
        )

    def _meets(self, mind: Mind, need: Need) -> bool:
        activity = mind.goal.activity
        change = self.config.effects.get(activity, {}).get(need, 0.0)
        change += self.config.finishing.get(activity, {}).get(need, 0.0)
        return change < 0 and (not self._placed(mind) or self._supplied(mind, need) > 0)

    def _interrupt(self, mind: Mind) -> None:
        """Drop what they're doing, held or not, to decide again now. A stay cut short brings
        none of its `finishing`."""
        logger.debug("%s stops %s for %s", mind.npc.id, mind.goal, sorted(mind.pressed))
        mind.held, mind.finishes = None, False
        walk, mind.walk = mind.walk, None
        if walk is not None:
            self.movement.stop(mind.npc.id)
        self._decide(mind)

    def _update_needs(self, hours: float) -> None:
        if hours <= 0:
            return
        positions = self.movement.entities()
        config = self.config
        for mind in self.minds.values():
            activity = mind.goal.activity
            sleeping = activity is Activity.SLEEP and mind.walk is None
            effects = self._effects(mind)
            for need in Need:
                rate = self._rise(mind.npc, need)
                if sleeping:
                    rate *= config.rise_asleep.get(need, 0.0)
                effect = effects.get(need, 0.0)
                if effect > 0 or (effect < 0 and self._eating(mind, need)):
                    rate += effect
                elif effect == 0 and mind.walk is None:
                    mind.eating.pop(need, None)
                mind.needs[need] = _clamp(mind.needs[need] + rate * hours)
            mind.needs[Need.FINANCES] = self._finances(mind.npc)
            if not self._home_bound(mind) and self._has_company(mind.npc.id, positions):
                mind.needs[Need.SOCIAL] = _clamp(mind.needs[Need.SOCIAL] - config.company * hours)

    def _eating(self, mind: Mind, need: Need) -> bool:
        """Whether their place meets `need` now: from when it reaches its appetite until it's
        met or the stay ends."""
        level = mind.needs[need]
        if level <= 0:
            mind.eating.pop(need, None)
        elif level >= self.config.urgency[need].appetite:
            mind.eating[need] = mind.since
        return mind.eating.get(need) == mind.since

    def _effects(self, mind: Mind) -> Mapping[Need, float]:
        if mind.walk is not None:
            return self.config.walking
        effects = self.config.effects.get(mind.goal.activity, {})
        if self._placed(mind):
            return {need: rate * self._supplied(mind, need) for need, rate in effects.items()}
        if mind.goal.activity is Activity.TALK and Need.SOCIAL in effects:
            relief = effects[Need.SOCIAL] / self._sociable(mind.npc)
            if mind.goal.target == PLAYER_ID:
                relief *= self.config.player_relief
            return {**effects, Need.SOCIAL: relief}
        return effects

    def _placed(self, mind: Mind) -> bool:
        return mind.goal.activity not in UNPLACED and not _painting(mind)

    def _supplied(self, mind: Mind, need: Need) -> float:
        """How much of their place's effect on `need` reaches them: all of a meal they've
        started, even if it was the last or the place shuts."""
        meal = self.config.urgency[need].appetite > 0 and mind.eating.get(need) == mind.since
        return 1.0 if meal else self._supply(mind.goal, need)

    def _supply(self, goal: Goal, need: Need) -> float:
        supply = self._call(self.hooks.supply, goal, need)
        return _clamp(supply) if isinstance(supply, int | float) else 1.0

    def _rise(self, npc: Npc, need: Need) -> float:
        if need is Need.INSPIRATION and npc.craft is None:
            return 0.0
        weights = self.config.rise_values.get(need, {})
        rise = self.config.rise.get(need, 0.0) + sum(w * npc.values[v] for v, w in weights.items())
        if need is not Need.SOCIAL:
            return rise
        sociable = self._sociable(npc)
        return rise * sociable if rise > 0 else rise / sociable

    def _sociable(self, npc: Npc) -> float:
        return trait_factor(self.traits_of(npc.id).sociability, self.config.sociability_spread)

    def traits_of(self, npc: Id) -> Traits:
        """Their traits from the cast, or neutral ones."""
        return self.traits.get(npc, NEUTRAL)

    def _has_company(self, npc: Id, positions: dict[Id, Point]) -> bool:
        here = positions[npc]
        return any(
            there.map == here.map and math.dist(here, there) <= self.config.near
            for other, there in positions.items()
            if other != npc
        )

    def _decide(self, mind: Mind) -> None:
        if mind.finishes:
            self._finish(mind)
        if self._asleep(mind):
            self._sleep(mind)
            return
        mind.pressed = self._critical(mind)
        situation = self._situation(mind)
        mind.mural = situation.mural
        options = scores(situation, self.places, self.config)
        if mind.nudge is not None:
            (goal, bonus), mind.nudge = mind.nudge, None
            if goal in options:
                options[goal] += bonus
        mind.options = {
            str(goal): round(value, 3) for goal, value in best_per_activity(options).values()
        }
        self._begin(mind, choose(options, self.rng, self.config.temperature))

    def _situation(self, mind: Mind) -> Situation:
        npc, now = mind.npc, self.clock.now
        known = (
            {rel.about: rel for rel in self.relationships.relationships(npc.id)}
            if self.relationships
            else {}
        )
        others = []
        for other, position in self.movement.entities().items():
            if other == npc.id or (other not in self.minds and other != PLAYER_ID):
                continue
            rel = as_of(known.get(other) or meet(npc, other), now, traits=self.traits_of(npc.id))
            others.append(
                Other(
                    other,
                    position,
                    affinity(rel, self.config),
                    self._place_of(other, position),
                    self._available(mind, other),
                )
            )
        news = self._call(self.hooks.news_interest, npc)
        craft = npc.craft.medium if npc.craft else None
        mural = self._call(self.hooks.mural_wall, npc) if craft is Medium.MURAL else None
        return Situation(
            npc.values,
            mind.needs,
            self.clock.time_of_day,
            self.movement.position(npc.id),
            npc.home,
            mind.bedtime,
            others,
            mind.goal,
            _clamp(news) if isinstance(news, int | float) else 0.0,
            craft,
            mural if isinstance(mural, MuralSpot) else None,
            self._supply,
            self._work(mind),
            lambda goal: self._price(self.hooks.price, npc, goal),
            lambda goal: self._price(self.hooks.earnings, npc, goal),
        )

    def _finish(self, mind: Mind) -> None:
        """At the end of a stay: apply `finishing`, and hand over whatever they made."""
        mind.finishes = False
        activity = mind.goal.activity
        for need, change in self.config.finishing.get(activity, {}).items():
            mind.needs[need] = _clamp(mind.needs[need] + change)
        if activity is Activity.CREATE:
            wall = mind.goal.target if _paints(mind.npc) else None
            self._call(self.hooks.create, mind.npc, wall)

    def _place_of(self, entity: Id, position: Point) -> str | None:
        mind = self.minds.get(entity)
        if mind and mind.goal.activity in GOING_TO_A_PLACE and not _painting(mind):
            return mind.goal.target
        location = self.places.at(position)
        return location.id if location else None

    def _available(self, seeker: Mind, other: Id) -> bool:
        if other == PLAYER_ID and seeker.npc.id in self.leave_player_alone:
            return False
        if seeker.cooldowns.get(other, self.clock.now) > self.clock.now:
            return False
        mind = self.minds.get(other)
        return mind is None or not (
            mind.paused or mind.held or self._home_bound(mind) or self._asleep(mind)
        )

    def _home_bound(self, mind: Mind) -> bool:
        home, goal = mind.npc.home, mind.goal
        if goal == Goal(Activity.WORK, home):
            return self.places.location(home).kind is LocationKind.HOUSE
        return goal.activity in AT_HOME or goal == Goal(Activity.CREATE, home)

    def _begin(self, mind: Mind, goal: Goal) -> None:
        mind.goal, mind.since, mind.until, mind.chases = goal, self.clock.now, None, 0
        mind.nudge, mind.finishes, mind.interrupted = None, False, None
        self._publish(mind)
        match goal.activity:
            case Activity.IDLE:
                self._arrive(mind)
            case Activity.WANDER:
                tile = self._wander_tile(mind)
                if tile is None:
                    self._arrive(mind)
                else:
                    self._walk(mind, tile)
            case Activity.SEEK:
                self._walk(mind, self._tile_of(goal.target))
            case Activity.CREATE if mind.mural is not None and _paints(mind.npc):
                self._walk(mind, mind.mural.tile)
            case _:
                self._walk(mind, goal.target)

    def _sleep(self, mind: Mind) -> None:
        self._begin(mind, Goal(Activity.SLEEP, mind.npc.home))

    def _take_up(self, mind: Mind) -> None:
        assert mind.held is not None
        target, goal = mind.held
        mind.until, mind.nudge, mind.finishes, mind.interrupted = None, None, False, None
        if mind.goal != goal:
            mind.goal, mind.since = goal, self.clock.now
            self._publish(mind)
        self._walk(mind, target)

    def _walk(self, mind: Mind, target: Tile | MapTile | str | None) -> None:
        mind.walk = None
        if target is None:
            self._arrive(mind)
            return
        walk = self.movement.walk_to(mind.npc.id, target)
        mind.walk = walk
        walk.add_done_callback(self._finished.append)

    def _settle(self, walk: Walk) -> None:
        mind = self.minds[walk.entity]
        if mind.walk is not walk or mind.paused:
            return
        mind.walk = None
        if mind.held:
            return
        if walk.outcome is Outcome.ARRIVED:
            self._arrive(mind)
        else:
            logger.debug("%s's walk for %s ended %s", mind.npc.id, mind.goal, walk.outcome)
            self._begin(mind, Goal(Activity.IDLE))

    def _arrive(self, mind: Mind) -> None:
        goal = mind.goal
        if goal.activity is Activity.SEEK and self._approach(mind):
            return
        if goal.activity is Activity.NEWS:
            self._call(self.hooks.read_news, mind.npc)
        if goal.activity is Activity.SLEEP:
            mind.until = self._next(mind.wake) + self._minutes((0, self.config.lie_in))
        elif goal.activity is Activity.WORK and (due := self._due(mind)) is not None:
            mind.until, mind.finishes = due.end, True
        else:
            now = self.clock.now
            dwell = self.config.dwell.get(goal.activity, (5, 15))
            mind.until, mind.finishes = now + self._minutes(dwell), True
            if goal.activity is Activity.WORK:
                mind.until = min(mind.until, max(mind.staying_on or now, now))

    def _approach(self, mind: Mind) -> bool:
        """At the end of a walk to someone: talk, hang around, or follow them. True if the NPC
        has moved on to something other than hanging around."""
        npc, other = mind.npc.id, mind.goal.target
        assert other is not None
        if other not in self.movement.entities() or not self._available(mind, other):
            self._give_up(mind, other)
            return True
        if self.movement.distance(npc, other) <= self.config.talk_range:
            if self._call(self.hooks.request_conversation, npc, other):
                self.pause(npc, other)
                self.pause(other, npc)
                return True
            mind.cooldowns[other] = self.clock.now + timedelta(minutes=self.config.seek_cooldown)
            return False
        if mind.chases < self.config.chases:
            mind.chases += 1
            self._walk(mind, self._tile_of(other))
            return True
        self._give_up(mind, other)
        return True

    def _give_up(self, mind: Mind, other: Id) -> None:
        mind.cooldowns[other] = self.clock.now + timedelta(minutes=self.config.seek_cooldown)
        self._decide(mind)

    def _call[*Args](self, hook: Callable[[*Args], object], *args: *Args) -> object:
        try:
            return hook(*args)
        except Exception:
            logger.exception("%r failed for %r", hook, args)
            return None

    def _tile_of(self, entity: Id | None) -> MapTile | None:
        if entity is None or entity not in self.movement.entities():
            return None
        position = self.movement.position(entity)
        return MapTile(map=position.map, x=max(round(position.x), 0), y=max(round(position.y), 0))

    def _wander_tile(self, mind: Mind) -> MapTile | None:
        """Somewhere near them that isn't a house, or near the door outside if they're indoors."""
        here = self.movement.position(mind.npc.id)
        door = next((d for d in self.movement.town.doors if d.inside.map == here.map), None)
        if door is not None:
            here = Point(door.outside.x, door.outside.y, door.outside.map)
        town, reach = self.movement.maps[here.map], self.config.wander_radius
        for _ in range(20):
            x = round(here.x) + self.rng.randint(-reach, reach)
            y = round(here.y) + self.rng.randint(-reach, reach)
            if not town.walkable(x, y):
                continue
            location = self.places.at(Point(x, y, here.map))
            if location is None or location.kind is not LocationKind.HOUSE:
                return MapTile(map=here.map, x=x, y=y)
        return None

    def _at_home(self, mind: Mind) -> bool:
        location = self.places.at(self.movement.position(mind.npc.id))
        return location is not None and location.id == mind.npc.home

    def _next(self, hour: float) -> datetime:
        now = self.clock.now
        at = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(hours=hour)
        return at if at > now else at + timedelta(days=1)

    def _minutes(self, bounds: tuple[float, float]) -> timedelta:
        return timedelta(minutes=self.rng.uniform(*bounds))

    def _publish(self, mind: Mind) -> None:
        self.bus.publish(GoalChosen(mind.npc.id, mind.goal.activity.value, mind.goal.target))


def _clamp(value: float) -> float:
    return min(max(value, 0.0), 1.0)


def _wage(npc: Npc) -> bool:
    return npc.pay is not None and npc.pay.kind is PayKind.WAGE


def _paints(npc: Npc) -> bool:
    return npc.craft is not None and npc.craft.medium is Medium.MURAL


def _painting(mind: Mind) -> bool:
    return mind.goal.activity is Activity.CREATE and _paints(mind.npc)


def behaviour_of(app: Starlette) -> Behaviour:
    """The server's `Behaviour` on `app.state.behaviour`, created with N1's NPCs on first use."""
    if not hasattr(app.state, "behaviour"):
        app.state.behaviour = create_behaviour(app)
    return app.state.behaviour


def create_behaviour(
    app: Starlette,
    *,
    config: BehaviourConfig = DEFAULT_CONFIG,
    seed: int | None = None,
    npcs: Iterable[Npc] | None = None,
    traits: Mapping[Id, Traits] | None = None,
) -> Behaviour:
    from simile.memory import memory_of
    from simile.npc import load_npcs
    from simile.sim import world_of
    from simile.world import movement_of

    world = world_of(app)
    return Behaviour(
        world.clock,
        world.bus,
        movement_of(app),
        load_npcs() if npcs is None else npcs,
        memory_of(app),
        config=config,
        seed=seed,
        traits=cast_traits() if traits is None else traits,
    )
