import sys
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Protocol

from starlette.applications import Starlette

from simile.schema import (
    PLAYER_ID,
    Bionic,
    Body,
    Id,
    InteractionEvent,
    Item,
    Memory,
    MemoryKind,
    Npc,
    Relationship,
)
from simile.sim import Clock
from simile.social.bionics import against, looks, seen_in, sighting, tolerance, unease
from simile.social.config import DEFAULT_BIONICS, BionicsConfig
from simile.social.relationship import apply_events, as_of, meet
from simile.social.weapons import armed, carrying, noticed, wariness, wary
from simile.voicing.distance import apart
from simile.world.movement import Movement


class Store(Protocol):
    def relationship(self, owner: str, about: str) -> Relationship | None: ...

    def recall(
        self,
        owner: str,
        now: datetime,
        *,
        about: str | None = None,
        kind: MemoryKind | None = None,
        k: int = 5,
    ) -> list[Memory]: ...

    def add(self, *records: Memory | Relationship) -> None: ...


class Sightings:
    """Residents seeing the player's bionics, each one once, and any weapon they carry. Tick it
    on the sim loop."""

    def __init__(
        self,
        store: Store,
        clock: Clock,
        npcs: Mapping[Id, Npc],
        movement: Movement,
        body: Callable[[], Body],
        awake: Callable[[Id], bool],
        *,
        carried: Callable[[], Sequence[Item]] = lambda: (),
        config: BionicsConfig = DEFAULT_BIONICS,
    ) -> None:
        self.store = store
        self.clock = clock
        self.npcs = npcs
        self.movement = movement
        self.body = body
        self.awake = awake
        self.carried = carried
        self.config = config
        self._seen: dict[Id, dict[Bionic, datetime]] = {}
        self._noticed: set[Id] = set()
        self._elapsed = 0.0

    def tick(self, dt: float) -> None:
        self._elapsed += dt
        if self._elapsed >= self.config.look_every - 1e-9:
            self._elapsed = 0.0
            self.look()

    def look(self) -> None:
        """Each resident awake within sight of the player sees the bionics new to them, and the
        weapon if they haven't since the player last put it away."""
        fitted, is_armed = self.body().bionics, armed(self.carried())
        if not is_armed:
            self._noticed.clear()
        if not fitted and not is_armed:
            return
        for npc in self.npcs:
            if not self.in_sight(npc):
                continue
            if new := [bionic for bionic in fitted if bionic not in self.seen(npc)]:
                self.see(npc, new)
            if is_armed and npc not in self._noticed:
                self.notice(npc)

    def in_sight(self, npc: Id) -> bool:
        """Whether `npc` is awake and can see the player now."""
        try:
            here, player = self.movement.position(npc), self.movement.position(PLAYER_ID)
        except KeyError:
            return False
        return apart(here, player) <= self.config.sight and self.awake(npc)

    def see(self, npc: Id, bionics: Sequence[Bionic]) -> Relationship:
        """`npc` sees `bionics` for the first time, and returns how they now feel about them."""
        now = self.clock.now
        events, memory = sighting(self.npcs[npc], bionics, now, self.config)
        after = self._felt(npc, events)
        self.store.add(memory, after)
        self.seen(npc).update(dict.fromkeys(bionics, now))
        return after

    def notice(self, npc: Id) -> None:
        """`npc` sees the player armed. It leaves no memory, so the pistol is out of their prompts
        once it's put away, only a dent in the trust of anyone wary."""
        self._noticed.add(npc)
        resident = self.npcs[npc]
        if wary(resident, self.config):
            self.store.add(self._felt(npc, [noticed(resident, self.clock.now, self.config)]))

    def _felt(self, npc: Id, events: Sequence[InteractionEvent]) -> Relationship:
        now = self.clock.now
        stored = self.store.relationship(npc, PLAYER_ID)
        before = as_of(stored, now) if stored else meet(self.npcs[npc], PLAYER_ID)
        return apply_events(before, events, now)

    def seen(self, npc: Id) -> dict[Bionic, datetime]:
        """When `npc` first saw each bionic, read from their memories the first time it's asked."""
        if npc not in self._seen:
            memories = self.store.recall(
                npc, self.clock.now, about=PLAYER_ID, kind=MemoryKind.OBSERVATION, k=sys.maxsize
            )
            found: dict[Bionic, datetime] = {}
            for memory in sorted(memories, key=lambda memory: memory.timestamp):
                for bionic in seen_in(memory):
                    found.setdefault(bionic, memory.timestamp)
            self._seen[npc] = found
        return self._seen[npc]

    def unease(self, npc: Npc) -> float:
        """B1's `unease` hook: how much the bionics `npc` has seen or sees now, and the weapon
        they've seen on this outing or see now, put them off, up to 1."""
        return min(self._bionics_unease(npc) + self._weapon_unease(npc), 1.0)

    def _weapon_unease(self, npc: Npc) -> float:
        if not armed(self.carried()):
            return 0.0
        if npc.id not in self._noticed and not self.in_sight(npc.id):
            return 0.0
        return against(-wariness(npc.values, self.config), self.config)

    def _bionics_unease(self, npc: Npc) -> float:
        fitted = self.body().bionics
        if not fitted:
            return 0.0
        feeling = tolerance(npc.values, self.config)
        if not unease(feeling, fitted, self.config):
            return 0.0
        seen = fitted if self.in_sight(npc.id) else self.seen(npc.id)
        known = [bionic for bionic in fitted if bionic in seen]
        return unease(feeling, known, self.config)

    def looks(self, npc: Id) -> str | None:
        """What `npc` can see of the player face to face, for a prompt, or None if there's nothing
        out of the ordinary."""
        parts = [self._bionics_looks(npc)]
        if armed(self.carried()):
            parts.append(carrying(self.config.player_name, self.npcs[npc], self.config))
        return " ".join(filter(None, parts)) or None

    def _bionics_looks(self, npc: Id) -> str | None:
        fitted = self.body().bionics
        if not fitted:
            return None
        seen, now = self.seen(npc), self.clock.now
        new = [b for b in fitted if b not in seen or now - seen[b] < self.config.new_for]
        feeling = tolerance(self.npcs[npc].values, self.config)
        return looks(self.config.player_name, fitted, feeling, new, self.config)


def sightings_of(app: Starlette) -> Sightings:
    """The server's `Sightings`, made on first use."""
    if not hasattr(app.state, "sightings"):
        from simile.behaviour import Activity, behaviour_of
        from simile.memory import memory_of
        from simile.persistence import player_of

        behaviour = behaviour_of(app)
        app.state.sightings = Sightings(
            memory_of(app),
            behaviour.clock,
            behaviour.npcs,
            behaviour.movement,
            lambda: player_of(app).body,
            lambda npc: behaviour.goal(npc).activity is not Activity.SLEEP,
            carried=lambda: player_of(app).items,
        )
    return app.state.sightings
