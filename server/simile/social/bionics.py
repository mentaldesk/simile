from collections.abc import Mapping, Sequence
from datetime import datetime

from simile.schema import (
    LEGS,
    PLAYER_ID,
    Aspect,
    Bionic,
    CoreValue,
    InteractionEvent,
    Memory,
    MemoryKind,
    Npc,
)
from simile.social.config import DEFAULT_BIONICS, BionicsConfig

TOPIC = "bionics"
LEG_NAMES: dict[Bionic, str] = {
    **{legs: legs.replace("_", " ") for legs in LEGS},
    Bionic.BIONIC_LEGS: "bionic legs",
    Bionic.BIONIC_LEGS_2: "faster bionic legs",
    Bionic.BIONIC_LEGS_3: "fastest bionic legs",
}
FEET_NAMES: dict[Bionic, str] = {
    Bionic.SPRING_FEET: "spring feet",
    Bionic.SPRING_FEET_2: "higher spring feet",
}
CELL_NAMES: dict[Bionic, str] = {
    Bionic.POWER_CELL: "power cell",
    Bionic.POWER_CELL_2: "bigger power cell",
    Bionic.POWER_CELL_3: "biggest power cell",
}
PLURAL: frozenset[Bionic] = frozenset({*LEG_NAMES, *FEET_NAMES})
NAMES: dict[Bionic, str] = {
    **LEG_NAMES,
    **FEET_NAMES,
    **CELL_NAMES,
    Bionic.DATAJACK: "datajack",
    Bionic.INFRARED_EYE: "infrared eye",
}
FITTED: dict[Bionic, str] = {
    **LEG_NAMES,
    **FEET_NAMES,
    **{cell: f"a {name}" for cell, name in CELL_NAMES.items()},
    Bionic.DATAJACK: "a datajack",
    Bionic.INFRARED_EYE: "an infrared eye",
}
LOOKS: dict[Bionic, str] = {
    **{legs: f"{name} where their own legs were" for legs, name in LEG_NAMES.items()},
    **{feet: f"{name} where their own feet were" for feet, name in FEET_NAMES.items()},
    **{cell: f"a {name}'s charging port low on their belly" for cell, name in CELL_NAMES.items()},
    Bionic.DATAJACK: "a datajack socket in the back of their neck",
    Bionic.INFRARED_EYE: "an infrared eye that glows faintly red in place of one of their own",
}
FEELS: dict[int, str] = {
    -2: "Bionics on a person repel you: it isn't natural, and you'd rather keep your distance.",
    -1: "Bionics make you uneasy.",
    0: "Bionics don't much bother you either way.",
    1: "You find bionics interesting.",
    2: "Bionics fascinate you.",
}
FELT: dict[int, str] = {
    -2: "It isn't natural, and it turned my stomach.",
    -1: "It made me uneasy.",
    0: "",
    1: "I'd like a closer look.",
    2: "Fascinating: I'd love to know how it works.",
}


def tolerance(values: Mapping[CoreValue, float], config: BionicsConfig = DEFAULT_BIONICS) -> float:
    """How a resident takes to bionics, from -1 (strongly against) to 1, by their values."""
    weights = config.tolerance_weights
    return _clamp(sum(w * (values[value] - 0.5) for value, w in weights.items()), -1.0, 1.0)


def level(tolerance: float, config: BionicsConfig = DEFAULT_BIONICS) -> int:
    """-2 strongly against, -1 against, 0 barely minds, 1 for and 2 strongly for."""
    strength = 2 if abs(tolerance) >= config.strongly else int(abs(tolerance) >= config.mildly)
    return strength if tolerance > 0 else -strength


def strongly_against(npc: Npc, config: BionicsConfig = DEFAULT_BIONICS) -> bool:
    return level(tolerance(npc.values, config), config) == -2


def stands_out(bionics: Sequence[Bionic], config: BionicsConfig = DEFAULT_BIONICS) -> float:
    """How much `bionics` catch the eye together, up to 1."""
    return min(sum(config.stands_out.get(bionic, 0.0) for bionic in bionics), 1.0)


def unease(
    tolerance: float, seen: Sequence[Bionic], config: BionicsConfig = DEFAULT_BIONICS
) -> float:
    """How much the bionics they've seen put them off: none within `mildly` of 0, then up to 1."""
    against = max(-tolerance - config.mildly, 0.0) / (1 - config.mildly)
    return against * stands_out(seen, config)


def looks(
    name: str,
    bionics: Sequence[Bionic],
    tolerance: float,
    new: Sequence[Bionic] = (),
    config: BionicsConfig = DEFAULT_BIONICS,
) -> str | None:
    """What a resident can see of the player, for a prompt, or None without bionics."""
    if not bionics:
        return None
    parts = [f"{name} has {_listed([LOOKS[bionic] for bionic in bionics])}."]
    if new := [bionic for bionic in bionics if bionic in new]:
        are = "is" if len(new) == 1 and new[0] not in PLURAL else "are"
        parts.append(f"The {_listed([NAMES[b] for b in new])} {are} new since you last saw them.")
    parts.append(FEELS[level(tolerance, config)])
    return " ".join(parts)


def sighting(
    npc: Npc, bionics: Sequence[Bionic], now: datetime, config: BionicsConfig = DEFAULT_BIONICS
) -> tuple[list[InteractionEvent], Memory]:
    """An R1 event for each of `bionics` `npc` first sees, by tolerance, and the memory of them."""
    feeling = tolerance(npc.values, config)
    events = [
        InteractionEvent(
            actor=PLAYER_ID,
            target=npc.id,
            action=f"turned up with {FITTED[bionic]}",
            aspects=list(Aspect),
            valence=feeling,
            magnitude=config.sighting * config.stands_out.get(bionic, 0.0),
            timestamp=now,
        )
        for bionic in bionics
    ]
    said = f"I saw that {config.player_name} has {_listed([LOOKS[b] for b in bionics])}."
    eye_catching = max(config.stands_out.get(bionic, 0.0) for bionic in bionics)
    memory = Memory(
        owner=npc.id,
        kind=MemoryKind.OBSERVATION,
        content=" ".join(filter(None, [said, FELT[level(feeling, config)]])),
        salience=min(config.salience + config.salience_feeling * abs(feeling) * eye_catching, 1.0),
        valence=feeling,
        timestamp=now,
        about=[PLAYER_ID],
        topics=[TOPIC, *(NAMES[bionic] for bionic in bionics)],
    )
    return events, memory


def seen_in(memory: Memory) -> list[Bionic]:
    """The bionics a memory of a sighting records."""
    if memory.kind is not MemoryKind.OBSERVATION or TOPIC not in memory.topics:
        return []
    return [bionic for bionic, name in NAMES.items() if name in memory.topics]


def _listed(items: Sequence[str]) -> str:
    return items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"


def _clamp(value: float, low: float, high: float) -> float:
    return min(max(value, low), high)
