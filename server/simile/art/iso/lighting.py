"""Lighting sets and the shared look. Standard library only, for Blender's Python too."""

import math
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class LightingSet:
    name: str
    hours: tuple[int, int]
    azimuth: float
    elevation: float
    sun_energy: float
    sun_colour: tuple[float, float, float]
    sky_colour: tuple[float, float, float]
    sky_strength: float
    sun_angle: float = 1.5
    emit: dict[str, float] = field(default_factory=dict)
    exposure: float = 0.0
    glow: float = 0.0

    def emits(self, kind: str) -> float:
        """How strongly lamps, neon, windows or screens glow in this set, from 0 to 1."""
        return self.emit.get(kind, 1.0)

    def params(self) -> dict[str, Any]:
        return asdict(self)


DAY_EMIT = {"lamp": 0.0, "neon": 0.12, "window": 0.1, "screen": 0.6, "water": 1.0}

SETS: dict[str, LightingSet] = {
    s.name: s
    for s in (
        LightingSet(
            "night",
            (21, 5),
            azimuth=150,
            elevation=50,
            sun_energy=0.35,
            sun_colour=(0.55, 0.68, 1.0),
            sky_colour=(0.04, 0.07, 0.18),
            sky_strength=0.45,
            emit={"lamp": 1.0, "neon": 1.0, "window": 1.0, "screen": 1.0, "water": 0.15},
            exposure=0.5,
            glow=1.0,
        ),
        LightingSet(
            "morning",
            (5, 11),
            azimuth=105,
            elevation=26,
            sun_energy=4.0,
            sun_colour=(1.0, 0.88, 0.74),
            sky_colour=(0.52, 0.62, 0.82),
            sky_strength=0.6,
            emit=DAY_EMIT,
            glow=0.25,
        ),
        LightingSet(
            "afternoon",
            (11, 17),
            azimuth=215,
            elevation=52,
            sun_energy=3.4,
            sun_colour=(1.0, 0.96, 0.9),
            sky_colour=(0.48, 0.6, 0.88),
            sky_strength=0.6,
            emit=DAY_EMIT,
            glow=0.25,
        ),
        LightingSet(
            "evening",
            (17, 21),
            azimuth=248,
            elevation=16,
            sun_energy=5.5,
            sun_colour=(1.0, 0.5, 0.25),
            sky_colour=(0.3, 0.27, 0.48),
            sky_strength=0.5,
            emit={"lamp": 0.7, "neon": 0.8, "window": 0.7, "screen": 0.9, "water": 0.5},
            glow=0.85,
        ),
    )
}

LOOK: dict[str, Any] = {
    "samples": 48,
    "segments": 16,
    "saturation": 0.6,
    "value": 0.78,
    "filter_width": 1.2,
    "view": "AgX - Medium High Contrast",
    "glow_radius": 10,
    "glow_strength": 0.85,
}

CROSSFADE_MINUTES = 60


def blend(hour: float) -> list[tuple[str, float]]:
    """The sets to draw at a sim-clock hour and their weights: one set, or two mid-crossfade."""
    names = list(SETS)
    half = CROSSFADE_MINUTES / 120
    for i, name in enumerate(names):
        since = (hour - SETS[name].hours[0] + 12) % 24 - 12
        if -half < since < half:
            x = (since + half) / (2 * half)
            weight = x * x * (3 - 2 * x)
            return [(names[i - 1], 1 - weight), (name, weight)]
    for name in names:
        start, end = SETS[name].hours
        if (start <= hour < end) if start < end else (hour >= start or hour < end):
            return [(name, 1.0)]
    raise ValueError(f"no lighting set covers {hour}")


def to_sun(azimuth: float, elevation: float) -> tuple[float, float, float]:
    """Unit vector towards the sun in Blender's axes (x east, y north, z up)."""
    a, e = math.radians(azimuth), math.radians(elevation)
    return math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)


def shadow_direction(azimuth: float) -> tuple[float, float]:
    """The way shadows fall on the map, as a unit step in tiles (x east, y south)."""
    a = math.radians(azimuth)
    return -math.sin(a), math.cos(a)
