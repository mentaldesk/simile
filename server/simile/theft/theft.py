from collections.abc import Callable, Mapping
from datetime import datetime
from typing import Protocol

from pydantic import BaseModel, ConfigDict, Field
from starlette.applications import Starlette

from simile.schema import (
    PLAYER_ID,
    Aspect,
    CoreValue,
    Id,
    InteractionEvent,
    Memory,
    MemoryKind,
    Npc,
    Player,
    Relationship,
    Signed,
    Unit,
)
from simile.sim import Clock
from simile.social import DEFAULT_BIONICS, apply_events, as_of, meet
from simile.street.finds import STASHES, Stash
from simile.world.movement import Movement

TOPIC = "theft"

MINDS: dict[CoreValue, float] = {
    CoreValue.SECURITY: 1.0,
    CoreValue.TRADITION: 1.0,
    CoreValue.OBEDIENCE: 0.5,
    CoreValue.COMPASSION: -0.5,
}


class TheftConfig(BaseModel):
    """How residents take to seeing the player search a house."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    minds: dict[CoreValue, Signed] = Field(
        default=MINDS,
        description="How each core value moves how much a resident minds: "
        "0.5 + sum(weight * (value - 0.5)), clamped to [least, 1]. Security and tradition most.",
    )
    least: Unit = Field(default=0.2, description="How much even the most easygoing resident minds.")
    seen: Unit = Field(
        default=0.2,
        description="The magnitude of R1's event for seeing the player search someone else's "
        "house. Its valence is minus how much they mind.",
    )
    home: Unit = Field(default=0.4, description="The magnitude when it's their own house.")
    aspects: tuple[Aspect, ...] = (Aspect.TRUST, Aspect.RESPECT)
    salience: Unit = Field(default=0.5, description="The salience of the memory of it.")
    salience_home: Unit = Field(default=0.8, description="The salience when it's their own house.")
    player_name: str = Field(default=DEFAULT_BIONICS.player_name, min_length=1)


DEFAULT_CONFIG = TheftConfig()


class Store(Protocol):
    def relationship(self, owner: str, about: str) -> Relationship | None: ...

    def add(self, *records: Memory | Relationship) -> None: ...


def minds(values: Mapping[CoreValue, float], config: TheftConfig = DEFAULT_CONFIG) -> float:
    """How much a resident minds seeing someone go through a house, from `least` to 1."""
    weighed = 0.5 + sum(w * (values[value] - 0.5) for value, w in config.minds.items())
    return min(max(weighed, config.least), 1.0)


def caught(
    npc: Npc,
    stash: Stash,
    owner: Npc | None,
    now: datetime,
    config: TheftConfig = DEFAULT_CONFIG,
) -> tuple[InteractionEvent, Memory]:
    """R1's event for `npc` seeing the player search `stash` in `owner`'s house, and their memory
    of it."""
    theirs = owner is not None and owner.id == npc.id
    feeling = -minds(npc.values, config)
    whose = "my house" if theirs else f"{owner.name}'s house" if owner else "someone's house"
    thing = stash.label[0].lower() + stash.label[1:]
    event = InteractionEvent(
        actor=PLAYER_ID,
        target=npc.id,
        action=f"went through the {thing} in {whose}",
        aspects=list(config.aspects),
        valence=feeling,
        magnitude=config.home if theirs else config.seen,
        timestamp=now,
    )
    memory = Memory(
        owner=npc.id,
        kind=MemoryKind.OBSERVATION,
        content=f"I saw {config.player_name} going through the {thing} in {whose}.",
        salience=config.salience_home if theirs else config.salience,
        valence=feeling,
        timestamp=now,
        about=[PLAYER_ID, *([owner.id] if owner and not theirs else [])],
        topics=[TOPIC],
    )
    return event, memory


class Theft:
    """Whoever is awake in the room seeing the player search a place in a house. Tick it on the
    sim loop."""

    def __init__(
        self,
        player: Player,
        movement: Movement,
        store: Store,
        clock: Clock,
        npcs: Mapping[Id, Npc],
        awake: Callable[[Id], bool],
        *,
        stashes: Mapping[Id, Stash] = STASHES,
        config: TheftConfig = DEFAULT_CONFIG,
    ) -> None:
        self.player = player
        self.movement = movement
        self.store = store
        self.clock = clock
        self.npcs = npcs
        self.awake = awake
        self.stashes = stashes
        self.config = config
        self.rooms = {
            thing.id: town.id
            for town in movement.maps.values()
            for thing in town.interactables
            if thing.id in stashes
        }
        self._handled = len(player.searched)

    def tick(self, dt: float) -> None:
        searched = self.player.searched
        for thing in searched[self._handled :]:
            if thing in self.stashes:
                self.search(self.stashes[thing])
        self._handled = len(searched)

    def search(self, stash: Stash) -> list[Id]:
        """The player has searched `stash`, and whoever sees it minds. Returns who saw."""
        owner = next((npc for npc in self.npcs.values() if npc.home == stash.house), None)
        witnesses = self.witnesses(self.rooms.get(stash.id))
        for npc in witnesses:
            self.see(self.npcs[npc], stash, owner)
        return witnesses

    def witnesses(self, room: Id | None) -> list[Id]:
        """The residents awake in `room`."""
        entities = self.movement.entities()
        return [
            npc
            for npc in self.npcs
            if npc in entities and entities[npc].map == room and self.awake(npc)
        ]

    def see(self, npc: Npc, stash: Stash, owner: Npc | None) -> Relationship:
        now = self.clock.now
        event, memory = caught(npc, stash, owner, now, self.config)
        stored = self.store.relationship(npc.id, PLAYER_ID)
        before = as_of(stored, now) if stored else meet(npc, PLAYER_ID)
        after = apply_events(before, [event], now)
        self.store.add(memory, after)
        return after


def theft_of(app: Starlette) -> Theft:
    """The server's `Theft`, made on first use."""
    if not hasattr(app.state, "theft"):
        from simile.behaviour import Activity, behaviour_of
        from simile.memory import memory_of
        from simile.persistence import player_of

        behaviour = behaviour_of(app)
        app.state.theft = Theft(
            player_of(app),
            behaviour.movement,
            memory_of(app),
            behaviour.clock,
            behaviour.npcs,
            lambda npc: behaviour.goal(npc).activity is not Activity.SLEEP,
        )
    return app.state.theft
