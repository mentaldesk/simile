import logging
import random
import sys
from collections.abc import Callable, Collection, Sequence
from datetime import datetime
from typing import Protocol

from starlette.applications import Starlette

from simile.conversation.player import PlayerConversations
from simile.schema import (
    PLAYER_ID,
    Id,
    Item,
    ItemKind,
    Memory,
    MemoryKind,
    Npc,
    Player,
    Relationship,
)
from simile.social import as_of, tolerance
from simile.social.bionics import level
from simile.story.config import DEFAULT_CONFIG, StoryConfig

logger = logging.getLogger(__name__)

LENS = Item(id="infrared_lens", kind=ItemKind.PART, name="Infrared lens", weight=0.2)
"""The part the clinic's infrared eye needs."""
KEPT = "lens_kept"
"""The topic of the keeper's memory of still having it."""
GIVEN = "lens_given"
"""The topic of the keeper's memory of giving it to the player."""
KEEPS = (
    "I've still got my old thermal camera at home. Its infrared lens is the part an infrared eye "
    "needs, and I'd give it to {player} once I trust them a little more."
)
GAVE = "I gave {player} the infrared lens out of my old thermal camera, for an infrared eye."
GIVES = "Here, I want you to have this: the infrared lens out of my old thermal camera."
FULL = "I've something for you, but your hands are full. Come back when you can carry it."


class Memories(Protocol):
    def relationship(self, owner: str, about: str) -> Relationship | None: ...

    def recall(
        self, owner: str, now: datetime, *, about: str | None = None, k: int = 5
    ) -> list[Memory]: ...

    def add(self, *records: Memory) -> None: ...


def keeper(
    npcs: Sequence[Npc],
    rng: random.Random,
    *,
    besides: Collection[Id] = (),
    config: StoryConfig = DEFAULT_CONFIG,
) -> Npc | None:
    """Who has the lens: drawn from those who take to bionics at `tolerates_from` or better, or
    else whoever takes to them best. Nobody in `besides` while anyone else would do."""
    residents = sorted(npcs, key=lambda npc: npc.id)
    tolerant = [npc for npc in residents if level(tolerance(npc.values)) >= config.tolerates_from]
    rng.shuffle(tolerant)
    pool = tolerant or sorted(residents, key=lambda npc: -tolerance(npc.values))
    return next((npc for npc in pool if npc.id not in besides), pool[0] if pool else None)


class Lens:
    """Once they've met, the keeper speaks of the lens when they trust the player
    `mentions_from`, and hands it over in a conversation with them once they trust them
    `gives_from`, if they can carry it."""

    def __init__(
        self,
        keeper: Npc,
        memory: Memories,
        now: Callable[[], datetime],
        player: Callable[[], Player],
        players: Callable[[], PlayerConversations | None],
        config: StoryConfig = DEFAULT_CONFIG,
    ) -> None:
        self.keeper = keeper
        self.memory = memory
        self.now = now
        self.player = player
        self.players = players
        self.config = config
        topics = {
            topic
            for remembered in memory.recall(keeper.id, now(), about=PLAYER_ID, k=sys.maxsize)
            for topic in remembered.topics
        }
        self.kept = KEPT in topics
        self.given = GIVEN in topics
        self._considered: set[str] = set()
        self._elapsed = config.lens_every

    def trusts(self, enough: float) -> bool:
        """Whether they've met the player and trust them `enough`."""
        stored = self.memory.relationship(self.keeper.id, PLAYER_ID)
        return stored is not None and as_of(stored, self.now()).trust >= enough

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed >= self.config.lens_every - 1e-9:
            self._elapsed = 0.0
            self.mention()
        self.hand_over()

    def mention(self) -> bool:
        """Remembers still having it, about the player, once trusting them enough to say so."""
        if self.kept or self.given or not self.trusts(self.config.mentions_from):
            return False
        self.kept = True
        self._remember(KEEPS, KEPT, salience=0.6, valence=0.2)
        return True

    def hand_over(self) -> bool:
        """Gives the player the lens, once a conversation waits on them, if trusted enough."""
        players = self.players()
        talk = players.talk() if players and not self.given else None
        if talk is None or talk.npc != self.keeper.id or talk.conversation.id in self._considered:
            return False
        waiting = talk.speaker == PLAYER_ID and talk.writing is None and not talk.queued
        spoken = any(line.speaker == self.keeper.id for line in talk.conversation.lines)
        if talk.refusing or talk.closing or not waiting or not spoken:
            return False
        self._considered.add(talk.conversation.id)
        if not self.trusts(self.config.gives_from):
            return False
        player = self.player()
        if player.load + LENS.weight > player.carry_limit + 1e-9:
            players.interject(self.keeper.id, FULL)
            return False
        if not players.interject(self.keeper.id, GIVES):
            return False
        player.items = [*player.items, LENS.model_copy()]
        self.given = True
        self._remember(GAVE, GIVEN, salience=0.8, valence=0.4)
        logger.info("%s gave the player the infrared lens", self.keeper.id)
        return True

    def _remember(self, text: str, topic: str, *, salience: float, valence: float) -> None:
        players = self.players()
        name = players.engine.player.name if players else "Visitor"
        self.memory.add(
            Memory(
                owner=self.keeper.id,
                kind=MemoryKind.OBSERVATION,
                content=text.format(player=name),
                salience=salience,
                valence=valence,
                timestamp=self.now(),
                about=[PLAYER_ID],
                topics=[topic],
            )
        )


def give(app: Starlette, config: StoryConfig = DEFAULT_CONFIG) -> Callable[[], None]:
    """Chooses the keeper from the world's seed and ticks their `Lens`, until the returned stop."""
    from simile.behaviour import behaviour_of
    from simile.memory import memory_of
    from simile.persistence import investigation_of, player_of
    from simile.sim import world_of
    from simile.story.town import world_seed

    incident = investigation_of(app).incident
    attackers = incident.attackers if incident else []
    npcs = list(behaviour_of(app).npcs.values())
    chosen = keeper(npcs, random.Random(f"lens/{world_seed()}"), besides=attackers, config=config)
    if chosen is None:
        return lambda: None
    world = world_of(app)
    lens = Lens(
        chosen,
        memory_of(app),
        lambda: world.clock.now,
        lambda: player_of(app),
        lambda: getattr(app.state, "players", None),
        config,
    )
    return world.loop.register(lens)
