from collections.abc import Mapping
from functools import lru_cache
from pathlib import Path
from types import MappingProxyType

from simile.schema import Id, Traits

NEUTRAL = Traits()


def trait_factor(trait: float, spread: float) -> float:
    """What a 0-1 trait multiplies by: 1 at 0.5, `spread` at 1 and 1 / `spread` at 0."""
    return spread ** (2 * trait - 1)


def traits_of(npc: Id) -> Traits:
    """The resident's traits in the world's cast, or neutral ones for anyone outside a cast."""
    return cast_traits().get(npc, NEUTRAL)


def cast_traits(data: Path | None = None) -> Mapping[Id, Traits]:
    """Each resident's traits in the data directory's cast, `$SIMILE_DB`'s by default. Empty
    without a cast, as in today's village."""
    from simile.casting.store import CAST_DIR, MANIFEST, data_directory

    data = data or data_directory()
    if data is None:
        return MappingProxyType({})
    manifest = data / CAST_DIR / MANIFEST
    try:
        stamp = manifest.stat().st_mtime_ns
    except OSError:
        return MappingProxyType({})
    return _read(manifest.parent.parent, stamp)


@lru_cache(maxsize=8)
def _read(data: Path, stamp: int) -> Mapping[Id, Traits]:
    from simile.casting.store import load_cast

    cast = load_cast(data)
    residents = cast.residents if cast else []
    return MappingProxyType({r.character.id: r.character.traits for r in residents})
