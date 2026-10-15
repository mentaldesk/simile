import logging
import math
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Protocol

from pydantic import JsonValue
from starlette.applications import Starlette

from simile.behaviour.config import DEFAULT_CONFIG, Activity, BehaviourConfig, Need
from simile.behaviour.events import GoalChosen
from simile.behaviour.scoring import (
    Goal,
    Other,
    Places,
    Situation,
    affinity,
    asleep,
    bedtime,
    best_per_activity,
    choose,
    scores,
    wake,
)
from simile.schema import PLAYER_ID, Conversation, Id, LocationKind, Npc, Relationship, Tile
from simile.sim import Clock, EventBus
from simile.social import as_of, meet
from simile.world.movement import Movement, Outcome, Point, Walk

logger = logging.getLogger(__name__)

type ConversationRequest = Callable[[Id, Id], bool]
type NewsReader = Callable[[Npc], None]
type LiveConversations = Callable[[], list[Conversation]]

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
)


def decline(a: Id, b: Id) -> bool:
    return False


def skip_news(npc: Npc) -> None:
    return None


def no_conversations() -> list[Conversation]:
    return []


class Hooks:
    """The interfaces other modules implement, stubbed until they do. See the README."""

    def __init__(self) -> None:
        self.request_conversation: ConversationRequest = decline
        self.read_news: NewsReader = skip_news
        self.conversations: LiveConversations = no_conversations

    def set(
        self,
        *,
        request_conversation: ConversationRequest | None = None,
        read_news: NewsReader | None = None,
        conversations: LiveConversations | None = None,
    ) -> Callable[[], None]:
        """Plug in the hooks given and return a function that puts back what they replaced."""
        given = {
            "request_conversation": request_conversation,
            "read_news": read_news,
            "conversations": conversations,
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
    ) -> None:
        self.clock = clock
        self.bus = bus
        self.movement = movement
        self.npcs = {npc.id: npc for npc in npcs}
        self.relationships = relationships
        self.config = config
        self.rng = random.Random(seed)
        self.hooks = Hooks()
        self.places = Places(movement.town)
        self.minds: dict[Id, Mind] = {}
        self._finished: list[Walk] = []
        self._elapsed = 0.0
        self._needs_at = clock.now

    def start(self) -> None:
        """Put every NPC who isn't on the map yet at home, and give them their first goal."""
        now, hour = self.clock.now, self.clock.time_of_day
        placed = self.movement.entities()
        self._needs_at = now
        for npc in self.npcs.values():
            if npc.id not in placed:
                self.movement.place(npc.id, npc.home)
            needs = {need: self.rng.uniform(*self.config.start_needs[need]) for need in Need}
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
            if asleep(hour, mind.bedtime, mind.wake):
                self._sleep(mind)
            elif mind.goal.activity is Activity.HOME:
                self._publish(mind)
                mind.until = now + self._minutes(self.config.start_dwell)
            else:
                self._decide(mind)

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
        mind.paused = True
        mind.until = None
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
        if mind.paused:
            mind.paused = False
            mind.until = self.clock.now

    def goal(self, npc: Id) -> Goal:
        return self.minds[npc].goal

    def needs(self, npc: Id) -> dict[Need, float]:
        return dict(self.minds[npc].needs)

    def state(self, npc: Id) -> dict[str, JsonValue]:
        """The NPC's goal, needs and last decision, for the debug overlay."""
        mind = self.minds[npc]
        return {
            "goal": str(mind.goal),
            "activity": mind.goal.activity.value,
            "target": mind.goal.target,
            "walking": mind.walk is not None,
            "paused": mind.paused,
            "since": mind.since.isoformat(),
            "until": mind.until.isoformat() if mind.until else None,
            "needs": {need.value: round(value, 3) for need, value in mind.needs.items()},
            "options": dict(mind.options),
            "bedtime": round(mind.bedtime, 2),
            "wake": round(mind.wake, 2),
        }

    def _think(self) -> None:
        now, hour = self.clock.now, self.clock.time_of_day
        hours = (now - self._needs_at) / timedelta(hours=1)
        self._needs_at = now
        self._update_needs(hours)
        for mind in self.minds.values():
            if mind.paused:
                continue
            if asleep(hour, mind.bedtime, mind.wake):
                if mind.goal.activity is not Activity.SLEEP:
                    self._sleep(mind)
            elif mind.walk is None and mind.until is not None and now >= mind.until:
                self._decide(mind)

    def _update_needs(self, hours: float) -> None:
        if hours <= 0:
            return
        positions = self.movement.entities()
        config = self.config
        for mind in self.minds.values():
            activity = mind.goal.activity
            sleeping = activity is Activity.SLEEP and mind.walk is None
            effects = config.walking if mind.walk is not None else config.effects.get(activity, {})
            for need in Need:
                rate = 0.0 if sleeping else self._rise(mind.npc, need)
                rate += effects.get(need, 0.0)
                mind.needs[need] = _clamp(mind.needs[need] + rate * hours)
            if activity not in AT_HOME and self._has_company(mind.npc.id, positions):
                mind.needs[Need.SOCIAL] = _clamp(mind.needs[Need.SOCIAL] - config.company * hours)

    def _rise(self, npc: Npc, need: Need) -> float:
        weights = self.config.rise_values.get(need, {})
        return self.config.rise.get(need, 0.0) + sum(w * npc.values[v] for v, w in weights.items())

    def _has_company(self, npc: Id, positions: dict[Id, Point]) -> bool:
        here = positions[npc]
        return any(
            math.dist(here, there) <= self.config.near
            for other, there in positions.items()
            if other != npc
        )

    def _decide(self, mind: Mind) -> None:
        if asleep(self.clock.time_of_day, mind.bedtime, mind.wake):
            self._sleep(mind)
            return
        options = scores(self._situation(mind), self.places, self.config)
        mind.options = {
            str(goal): round(value, 3) for goal, value in best_per_activity(options).values()
        }
        self._begin(mind, choose(options, self.rng, self.config.temperature))

    def _situation(self, mind: Mind) -> Situation:
        npc, now, hour = mind.npc, self.clock.now, self.clock.time_of_day
        known = (
            {rel.about: rel for rel in self.relationships.relationships(npc.id)}
            if self.relationships
            else {}
        )
        others = []
        for other, position in self.movement.entities().items():
            if other == npc.id or (other not in self.minds and other != PLAYER_ID):
                continue
            rel = as_of(known.get(other) or meet(npc, other), now)
            others.append(
                Other(
                    other,
                    position,
                    affinity(rel, self.config),
                    self._place_of(other, position),
                    self._available(mind, other, hour),
                )
            )
        return Situation(
            npc.values,
            mind.needs,
            hour,
            self.movement.position(npc.id),
            npc.home,
            mind.bedtime,
            others,
            mind.goal,
        )

    def _place_of(self, entity: Id, position: Point) -> str | None:
        mind = self.minds.get(entity)
        if mind and mind.goal.activity in GOING_TO_A_PLACE:
            return mind.goal.target
        location = self.places.at(position)
        return location.id if location else None

    def _available(self, seeker: Mind, other: Id, hour: float) -> bool:
        if seeker.cooldowns.get(other, self.clock.now) > self.clock.now:
            return False
        mind = self.minds.get(other)
        return mind is None or not (
            mind.paused or mind.goal.activity in AT_HOME or asleep(hour, mind.bedtime, mind.wake)
        )

    def _begin(self, mind: Mind, goal: Goal) -> None:
        mind.goal, mind.since, mind.until, mind.chases = goal, self.clock.now, None, 0
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
            case _:
                self._walk(mind, goal.target)

    def _sleep(self, mind: Mind) -> None:
        self._begin(mind, Goal(Activity.SLEEP, mind.npc.home))

    def _walk(self, mind: Mind, target: Tile | str | None) -> None:
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
        else:
            dwell = self.config.dwell.get(goal.activity, (5, 15))
            mind.until = self.clock.now + self._minutes(dwell)

    def _approach(self, mind: Mind) -> bool:
        """At the end of a walk to someone: talk, hang around, or follow them. True if the NPC
        has moved on to something other than hanging around."""
        npc, other = mind.npc.id, mind.goal.target
        assert other is not None
        hour = self.clock.time_of_day
        if other not in self.movement.entities() or not self._available(mind, other, hour):
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

    def _tile_of(self, entity: Id | None) -> Tile | None:
        if entity is None or entity not in self.movement.entities():
            return None
        position = self.movement.position(entity)
        return Tile(x=max(round(position.x), 0), y=max(round(position.y), 0))

    def _wander_tile(self, mind: Mind) -> Tile | None:
        here = self.movement.position(mind.npc.id)
        reach = self.config.wander_radius
        for _ in range(20):
            x = round(here.x) + self.rng.randint(-reach, reach)
            y = round(here.y) + self.rng.randint(-reach, reach)
            if not self.movement.town.walkable(x, y):
                continue
            location = self.places.at(Point(x, y))
            if location is None or location.kind is not LocationKind.HOUSE:
                return Tile(x=x, y=y)
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


def behaviour_of(app: Starlette) -> Behaviour:
    """The server's `Behaviour` on `app.state.behaviour`, created with N1's NPCs on first use."""
    if not hasattr(app.state, "behaviour"):
        app.state.behaviour = create_behaviour(app)
    return app.state.behaviour


def create_behaviour(
    app: Starlette, *, config: BehaviourConfig = DEFAULT_CONFIG, seed: int | None = None
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
        load_npcs(),
        memory_of(app),
        config=config,
        seed=seed,
    )
