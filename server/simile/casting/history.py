from datetime import datetime

from simile.casting.config import DEFAULT_CONFIG, CastingConfig
from simile.casting.model import Bond, Cast
from simile.memory import MemoryStore, Record
from simile.schema import Baseline, Flag, HookSide, Id, Memory, MemoryKind, Npc, Relationship
from simile.social import meet


def history(cast: Cast, now: datetime, config: CastingConfig = DEFAULT_CONFIG) -> list[Record]:
    """What the residents bring with them to a village starting at `now`: each bond's
    relationships, flags and memories on both sides, and everyone's past as `past` memories."""
    npcs = {npc.id: npc for npc in cast.npcs()}
    records: list[Record] = []
    for bond in cast.bonds:
        for side in (HookSide.ACTOR, HookSide.TARGET):
            records += _bond_side(bond, side, npcs, now, config)
    for resident in cast.residents:
        character = resident.character
        age = cast.age(character)
        records += [
            Memory(
                owner=character.id,
                kind=MemoryKind.PAST,
                content=past.content,
                salience=past.salience,
                valence=past.valence,
                timestamp=now - config.past_spacing * max(age - past.age, 0),
            )
            for past in character.past
        ]
    return records


def seeded(memory: MemoryStore, residents: list[Id], now: datetime) -> bool:
    """Whether the store already holds anything of these residents, such as a village that ran."""
    return any(memory.recall(id, now, k=1) or memory.relationships(id) for id in residents)


def _bond_side(
    bond: Bond, side: HookSide, npcs: dict[Id, Npc], now: datetime, config: CastingConfig
) -> list[Record]:
    kind = config.bonds[bond.kind]
    feeling = kind.side(side)
    owner, about = (
        (bond.actor, bond.target) if side is HookSide.ACTOR else (bond.target, bond.actor)
    )
    words = bond.actor_hook if side is HookSide.ACTOR else bond.target_hook
    met = meet(npcs[owner], about)
    scores = {
        "like": _clamp(met.like + feeling.like),
        "trust": _clamp(met.trust + feeling.trust),
        "respect": _clamp(met.respect + feeling.respect),
    }
    flags = []
    if kind.flag is not None and side is HookSide.TARGET:
        flags.append(
            Flag(
                id=f"cast_{bond.kind}",
                kind=kind.flag,
                owner=owner,
                about=about,
                description=kind.flag_description,
                created=now,
            )
        )
    first = feeling.memory.format(name=npcs[about].name.split()[0])
    return [
        Relationship(
            owner=owner,
            about=about,
            **scores,
            familiarity=feeling.familiarity,
            baseline=Baseline(**scores),
            flags=flags,
        ),
        Memory(
            owner=owner,
            kind=MemoryKind.PAST,
            content=f"{first} {words}" if words else first,
            salience=config.bond_salience,
            valence=feeling.valence,
            timestamp=now,
            about=[about],
        ),
    ]


def _clamp(score: float) -> float:
    return min(max(score, 0.0), 1.0)
