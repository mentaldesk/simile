import math
from collections.abc import Callable, Sequence

from starlette.applications import Starlette

from simile.conversation.player import PlayerConversations
from simile.conversation.telling import Stance
from simile.persistence import investigation_of, player_of
from simile.protocol import JournalMessage, PickUpMessage, hub_of
from simile.schema import PLAYER_ID
from simile.sim import LineSpoken, world_of
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.content import Clue, load_story
from simile.story.journal import Journal
from simile.world import Point, movement_of


class Recorder:
    """Journals what a resident tells the player or lies about as they speak, and clues found."""

    def __init__(
        self,
        journal: Journal,
        players: Callable[[], PlayerConversations | None],
        here: Callable[[], Point | None],
        changed: Callable[[], None],
        *,
        clues: Sequence[Clue] = (),
        config: StoryConfig = DEFAULT_CONFIG,
    ) -> None:
        self.journal = journal
        self.players = players
        self.here = here
        self.changed = changed
        self.clues = clues
        self.config = config

    def on_spoken(self, event: LineSpoken) -> None:
        line = event.line
        players = self.players()
        talk = players.talk() if players and line.speaker != PLAYER_ID else None
        if talk is None or talk.conversation.id != line.conversation_id:
            return
        name = talk.names.get(line.speaker, line.speaker)
        told = [
            self.journal.told(telling.fact, telling.knower, name, lie=telling.stance is Stance.LIE)
            for telling in talk.tellings.values()
            if telling.stance is not Stance.KEEP
        ]
        if any(told):
            self.changed()

    def on_pick_up(self, message: PickUpMessage) -> None:
        if (clue := self.clue_in_reach()) and self.journal.found(clue.id, clue.label):
            self.changed()

    def clue_in_reach(self) -> Clue | None:
        here = self.here()
        if here is None:
            return None
        near = [
            (distance, clue.id, clue)
            for clue in self.clues
            if clue.map == here.map
            and (distance := math.dist(here, (clue.x, clue.y))) <= self.config.clue_reach
        ]
        return min(near)[2] if near else None


def record(app: Starlette, config: StoryConfig = DEFAULT_CONFIG) -> Callable[[], None]:
    """Keeps the journal and sends it on connect and each change, until the returned stop."""
    world, hub, movement = world_of(app), hub_of(app), movement_of(app)
    investigation = investigation_of(app)
    journal = Journal(investigation, lambda: world.clock.now, lambda: player_of(app))

    def message() -> JournalMessage:
        return JournalMessage(entries=investigation.journal)

    recorder = Recorder(
        journal,
        lambda: getattr(app.state, "players", None),
        lambda: movement.entities().get(PLAYER_ID),
        lambda: hub.broadcast(message()),
        clues=load_story().clues,
        config=config,
    )
    stops = [
        world.bus.subscribe(LineSpoken, recorder.on_spoken),
        hub.subscribe(PickUpMessage, recorder.on_pick_up),
        hub.greet(message),
    ]

    def stop() -> None:
        for each in reversed(stops):
            each()

    return stop
