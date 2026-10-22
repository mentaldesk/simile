import math
from collections.abc import Callable, Sequence

from starlette.applications import Starlette

from simile.conversation.player import PlayerConversations
from simile.conversation.telling import Stance
from simile.persistence import investigation_of, player_of
from simile.player.pickups import Claim, claimers_of
from simile.protocol import JournalMessage, hub_of
from simile.schema import PLAYER_ID
from simile.sim import LineSpoken, world_of
from simile.story.config import DEFAULT_CONFIG, StoryConfig
from simile.story.content import Clue, load_story
from simile.story.journal import Journal
from simile.story.saying import says
from simile.world import Point


class Recorder:
    """Journals what a resident tells the player, a cover once they've said it, and clues found."""

    def __init__(
        self,
        journal: Journal,
        players: Callable[[], PlayerConversations | None],
        changed: Callable[[], None],
        *,
        clues: Sequence[Clue] = (),
        config: StoryConfig = DEFAULT_CONFIG,
    ) -> None:
        self.journal = journal
        self.players = players
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
        said = " ".join(
            each.text for each in talk.conversation.lines if each.speaker == line.speaker
        )
        told = [
            self.journal.told(telling.fact, telling.knower, name, lie=telling.stance is Stance.LIE)
            for telling in talk.tellings.values()
            if telling.stance is Stance.TELL
            or (telling.stance is Stance.LIE and says(said, telling.knower.cover or ""))
        ]
        if any(told):
            self.changed()

    def claim(self, here: Point) -> Claim | None:
        """The clue in reach, for `pick_up` to find unless a pile is nearer."""
        near = [
            (distance, clue.id, clue)
            for clue in self.clues
            if clue.map == here.map
            and (distance := math.dist(here, (clue.x, clue.y))) <= self.config.clue_reach
        ]
        if not near:
            return None
        distance, _, clue = min(near)
        return Claim(distance, lambda: self.find(clue))

    def find(self, clue: Clue) -> None:
        if self.journal.found(clue.id, clue.label):
            self.changed()


def record(app: Starlette, config: StoryConfig = DEFAULT_CONFIG) -> Callable[[], None]:
    """Keeps the journal and sends it on connect and each change, until the returned stop."""
    world, hub, claimers = world_of(app), hub_of(app), claimers_of(app)
    investigation = investigation_of(app)
    journal = Journal(investigation, lambda: world.clock.now, lambda: player_of(app))

    def message() -> JournalMessage:
        return JournalMessage(entries=investigation.journal)

    recorder = Recorder(
        journal,
        lambda: getattr(app.state, "players", None),
        lambda: hub.broadcast(message()),
        clues=load_story().clues,
        config=config,
    )
    claimers.append(recorder.claim)
    stops = [world.bus.subscribe(LineSpoken, recorder.on_spoken), hub.greet(message)]

    def stop() -> None:
        claimers.remove(recorder.claim)
        for each in reversed(stops):
            each()

    return stop
