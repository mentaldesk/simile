import logging
from collections.abc import Callable
from datetime import timedelta

from starlette.applications import Starlette

from simile.ambient.config import DEFAULT_CONFIG, AmbientConfig
from simile.ambient.events import Nudged
from simile.behaviour import Activity, Behaviour, Goal
from simile.conversation import ConversationEngine
from simile.schema import PLAYER_ID, Id, LocationKind
from simile.sim import ConversationEnded, ConversationStarted
from simile.voicing.distance import between

logger = logging.getLogger(__name__)


class Earshot:
    """The NPC conversations the player can hear, as I1 decides: one comes into earshot once the
    player is within `earshot` of a speaker, and leaves it once they're further than
    `out_of_earshot` from all of them. Follow the bus with `on_started` and `on_ended`."""

    def __init__(
        self, distance: Callable[[Id], float | None], config: AmbientConfig = DEFAULT_CONFIG
    ) -> None:
        self.distance = distance
        """From the player to an NPC, None if either isn't on the map."""
        self.config = config
        self.live: dict[str, tuple[Id, ...]] = {}
        self.heard: set[str] = set()

    def on_started(self, event: ConversationStarted) -> None:
        participants = tuple(event.conversation.participants)
        if PLAYER_ID not in participants:
            self.live[event.conversation.id] = participants

    def on_ended(self, event: ConversationEnded) -> None:
        self.live.pop(event.conversation.id, None)
        self.heard.discard(event.conversation.id)

    def update(self) -> set[str]:
        """The conversations in earshot now."""
        heard = set()
        for id, participants in self.live.items():
            near = [d for npc in participants if (d := self.distance(npc)) is not None]
            reach = self.config.out_of_earshot if id in self.heard else self.config.earshot
            if near and min(near) <= reach:
                heard.add(id)
        self.heard = heard
        return heard


class Director:
    """Nudges two residents near the player to talk when the player hasn't heard an NPC
    conversation for `quiet` seconds. Tick it on the sim loop."""

    def __init__(
        self,
        behaviour: Behaviour,
        engine: ConversationEngine,
        *,
        connected: Callable[[], bool] = lambda: True,
        config: AmbientConfig = DEFAULT_CONFIG,
    ) -> None:
        self.behaviour = behaviour
        self.engine = engine
        self.connected = connected
        self.earshot = Earshot(self.from_player, config)
        self.config = config
        self.heard_at = behaviour.clock.now
        self.nudged_at = behaviour.clock.now - timedelta(seconds=config.retry)
        self._elapsed = 0.0

    @property
    def config(self) -> AmbientConfig:
        return self.earshot.config

    @config.setter
    def config(self, config: AmbientConfig) -> None:
        self.earshot.config = config

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed >= self.config.look_every - 1e-9:
            self._elapsed = 0.0
            self.look()

    def look(self) -> tuple[Id, Id] | None:
        """Nudge a pair if it's been quiet long enough. Returns them, seeker first."""
        behaviour, config, now = self.behaviour, self.config, self.behaviour.clock.now
        listening = self.connected() and PLAYER_ID in behaviour.movement.entities()
        if not listening or self.earshot.update() or self.engine.talking(PLAYER_ID):
            self.heard_at = now
            return None
        if not config.enabled:
            return None
        if len(self.earshot.live) >= self.engine.config.max_conversations:
            return None
        if now - self.heard_at < timedelta(seconds=config.quiet):
            return None
        if now - self.nudged_at < timedelta(seconds=config.retry):
            return None
        pair = self.choose()
        if pair is None:
            return None
        seeker, target = pair
        if not behaviour.nudge(seeker, Goal(Activity.SEEK, target), config.bonus):
            return None
        self.nudged_at = now
        logger.info("%s  Nudged %s to seek out %s near the player", behaviour.clock, seeker, target)
        behaviour.bus.publish(Nudged(seeker, target))
        return pair

    def choose(self) -> tuple[Id, Id] | None:
        """The two keenest residents who would accept each other near the player, seeker first."""
        behaviour, engine, config = self.behaviour, self.engine, self.config
        position = behaviour.movement.position
        best: tuple[tuple[float, float], tuple[Id, Id]] | None = None
        for target in behaviour.npcs:
            heard = self.from_player(target)
            if heard is None or heard > config.earshot or behaviour.minds[target].walk is not None:
                continue
            for seeker in behaviour.npcs:
                if seeker == target or not self._free(seeker, target):
                    continue
                if behaviour.places.tiles(position(seeker), position(target)) > config.reach:
                    continue
                keen = min(engine.accept_score(seeker, target), engine.accept_score(target, seeker))
                if keen <= config.accept_bar:
                    continue
                key = (keen, -heard)
                if best is None or key > best[0]:
                    best = key, (seeker, target)
        return best[1] if best else None

    def from_player(self, npc: Id) -> float | None:
        try:
            return between(self.behaviour.movement, npc, PLAYER_ID)
        except KeyError:
            return None

    def _free(self, seeker: Id, target: Id) -> bool:
        if self._in_a_house(seeker) or self._in_a_house(target):
            return False
        return self.behaviour.available(seeker, target) and self.behaviour.available(target, seeker)

    def _in_a_house(self, npc: Id) -> bool:
        place = self.behaviour.places.at(self.behaviour.movement.position(npc))
        return place is not None and place.kind is LocationKind.HOUSE


def director_of(app: Starlette) -> Director:
    """The server's director on `app.state.ambient`, created on first use."""
    if not hasattr(app.state, "ambient"):
        from simile.behaviour import behaviour_of
        from simile.conversation import conversations_of
        from simile.protocol import hub_of

        hub = hub_of(app)
        app.state.ambient = Director(
            behaviour_of(app), conversations_of(app), connected=lambda: bool(hub.connections)
        )
    return app.state.ambient
