import random
from collections.abc import Sequence
from datetime import UTC, date, datetime

from simile.casting.choose import value_distance
from simile.casting.config import DEFAULT_CONFIG, CastingConfig
from simile.casting.model import Bond, Cast, CastError, Pin, Resident
from simile.schema import Character, HookKind, HookSide, Id, LocationKind
from simile.schema.character import MAX_AGE

type Hook = tuple[Id, int]


def village_houses() -> list[Id]:
    """The houses on the village map, which are the homes a cast can have."""
    from simile.world.map import load_map

    return [loc.id for loc in load_map().locations if loc.kind is LocationKind.HOUSE]


def bind(
    chosen: Sequence[Character],
    pins: Sequence[Pin] = (),
    seed: int = 0,
    game_date: date | None = None,
    *,
    houses: Sequence[Id] | None = None,
    config: CastingConfig = DEFAULT_CONFIG,
) -> Cast:
    """Give each resident a home, bind the pins, then bind open hooks between residents."""
    houses = list(village_houses() if houses is None else houses)
    if len(chosen) > len(houses):
        raise CastError(f"The village has {len(houses)} houses, too few for {len(chosen)}")
    game_date = game_date or datetime.now(UTC).date()
    for character in chosen:
        _check_age(character, game_date)
    rng = random.Random(f"{seed}:bind")
    homes = rng.sample(houses, len(chosen))
    binder = _Binder(chosen, rng, config)
    for pin in pins:
        binder.pin(pin)
    binder.draw()
    return Cast(
        game_date=game_date,
        seed=seed,
        residents=[Resident(character=c, home=home) for c, home in zip(chosen, homes, strict=True)],
        bonds=binder.bonds,
    )


def _check_age(character: Character, game_date: date) -> None:
    born = character.birth_year
    events = [memory.age for memory in character.past]
    oldest = max([*events, character.arrival.age if character.arrival else 0])
    if game_date.year - born < oldest:
        raise CastError(
            f"{game_date} is too early for {character.name}: born in {born}, with a past up to "
            f"age {oldest}"
        )
    if game_date.year - born > MAX_AGE:
        raise CastError(f"{game_date} is too late for {character.name}: born in {born}")


class _Binder:
    def __init__(self, chosen: Sequence[Character], rng: random.Random, config: CastingConfig):
        self.residents = {character.id: character for character in chosen}
        self.rng = rng
        self.config = config
        self.open: set[Hook] = {(c.id, i) for c in chosen for i in range(len(c.hooks))}
        self.bonded: set[frozenset[Id]] = set()
        self.bonds: list[Bond] = []

    def pin(self, pin: Pin) -> None:
        if missing := {pin.actor, pin.target} - self.residents.keys():
            raise CastError(f"Pinned {', '.join(sorted(missing))}, who isn't in the cast")
        if frozenset((pin.actor, pin.target)) in self.bonded:
            raise CastError(f"{pin.actor} and {pin.target} are pinned twice")
        actor, target = _sides(pin.kind)
        self._bond(
            pin.kind,
            pin.actor,
            pin.target,
            self._take(pin.actor, pin.kind, actor),
            self._take(pin.target, pin.kind, target),
            pinned=True,
        )

    def draw(self) -> None:
        order = list(self.residents)
        self.rng.shuffle(order)
        for id in order:
            for index, hook in enumerate(self.residents[id].hooks):
                if (id, index) not in self.open:
                    continue
                if (partner := self._partner(id, hook.kind, hook.side, order)) is None:
                    continue
                self.open.discard((id, index))
                mine = hook.description
                theirs = self._take(partner, hook.kind, _opposite(hook.side))
                if hook.side is HookSide.TARGET:
                    self._bond(hook.kind, partner, id, theirs, mine)
                else:
                    self._bond(hook.kind, id, partner, mine, theirs)

    def _partner(self, id: Id, kind: HookKind, side: HookSide, order: list[Id]) -> Id | None:
        me, bond = self.residents[id], self.config.bonds[kind]
        partners = [
            other
            for other in order
            if other != id
            and frozenset((id, other)) not in self.bonded
            and self._find(other, kind, _opposite(side)) is not None
            and self._plausible(me, self.residents[other], kind)
        ]
        if not partners:
            return None
        return max(partners, key=lambda o: -bond.fit * value_distance(me, self.residents[o]))

    def _plausible(self, a: Character, b: Character, kind: HookKind) -> bool:
        bond = self.config.bonds[kind]
        if bond.max_age_gap is not None and abs(a.birth_year - b.birth_year) > bond.max_age_gap:
            return False
        return not bond.same_origin or a.origin == b.origin

    def _find(self, id: Id, kind: HookKind, side: HookSide) -> int | None:
        hooks = self.residents[id].hooks
        return next(
            (
                i
                for i, hook in enumerate(hooks)
                if (id, i) in self.open and hook.kind is kind and hook.side is side
            ),
            None,
        )

    def _take(self, id: Id, kind: HookKind, side: HookSide) -> str | None:
        if (index := self._find(id, kind, side)) is None:
            return None
        self.open.discard((id, index))
        return self.residents[id].hooks[index].description

    def _bond(
        self,
        kind: HookKind,
        actor: Id,
        target: Id,
        actor_hook: str | None,
        target_hook: str | None,
        *,
        pinned: bool = False,
    ) -> None:
        self.bonded.add(frozenset((actor, target)))
        self.bonds.append(
            Bond(
                kind=kind,
                actor=actor,
                target=target,
                actor_hook=actor_hook,
                target_hook=target_hook,
                pinned=pinned,
            )
        )


def _sides(kind: HookKind) -> tuple[HookSide, HookSide]:
    return (HookSide.MUTUAL, HookSide.MUTUAL) if kind.mutual else (HookSide.ACTOR, HookSide.TARGET)


def _opposite(side: HookSide) -> HookSide:
    return {HookSide.ACTOR: HookSide.TARGET, HookSide.TARGET: HookSide.ACTOR}.get(side, side)
