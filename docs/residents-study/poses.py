"""The client's poses (`client/src/dolls/rig.ts`) as joint angles, for every approach that poses
a rig: #310's dolls and paint-then-cut through #329's Python port of the rig, and the 3D models
through Blender. Angles are in degrees; positive swings a hanging limb forward."""

import math

import study  # noqa: F401  # isort: skip
import dolls as port

TAU = math.tau
UNIT = 5.0
"""Atlas pixels a doll unit, #310's `doll.UNIT`."""
WALK_FRAMES = 8
"""Frames in every walk cycle shown here, at `WALK_MS` each."""
WALK_MS = 135

STAND = dict(port.STAND)
SIT = {"thigh": (86, 82), "knee": (86, 82), "foot": (0, 0)}


def pos(v: float) -> float:
    return max(0.0, v)


def walk(phase: float) -> dict:
    return port.walk(phase)


def sitting() -> dict:
    return {**STAND, **SIT, "lean": -3, "shoulder": (22, 18), "elbow": (38, 40)}


def stairs(phase: float) -> dict:
    t = TAU * phase

    def leg(t: float):
        thigh = 25 + 35 * math.sin(t)
        knee = max(4, thigh + 8)
        return thigh, knee, knee - thigh

    near, far = leg(t), leg(t + math.pi)
    return {
        "lean": 8,
        "nod": 4,
        "thigh": (near[0], far[0]),
        "knee": (near[1], far[1]),
        "foot": (near[2], far[2]),
        "shoulder": (-18 * math.sin(t), 18 * math.sin(t)),
        "elbow": (16, 16),
    }


def ladder_from_side(phase: float) -> dict:
    s = math.sin(TAU * phase)
    return {
        "lean": 4,
        "nod": -6,
        "thigh": (40 + 30 * s, 40 - 30 * s),
        "knee": (70 + 30 * s, 70 - 30 * s),
        "foot": (30 + 30 * s, 30 - 30 * s),
        "shoulder": (150 - 20 * s, 150 + 20 * s),
        "elbow": (30, 30),
    }


def ladder(phase: float) -> dict:
    """`rig.ts`'s climb up a ladder seen from behind, for the straight views."""
    s = math.sin(TAU * phase)
    return {
        **port.STRAIGHT,
        "arm": (160 + 15 * s, 160 - 15 * s),
        "elbow": (-25 + 15 * s, -25 - 15 * s),
        "leg": (4, 4),
        "thigh": (1 - 0.45 * pos(s), 1 - 0.45 * pos(-s)),
    }


RUN_AIR = 5
"""Units off the ground at the top of a running stride, as `rig.ts` lifts it."""
UNIT_M = 0.0185
"""A doll unit in metres, for the 3D model: #310's dolls stand about 99 units tall."""


def flight(t: float, air: float) -> float:
    return air * pos(abs(math.sin(t)) - 0.8) / 0.2


def run(phase: float) -> dict:
    """`rig.ts`'s run: leaning in, the knees high, the elbows bent and pumping, and off the
    ground between strides by `air` units."""
    t = TAU * phase

    def leg(t: float):
        thigh = 10 + 32 * math.sin(t)
        stance = 30 * pos(-math.cos(t)) ** 2
        knee = 16 + stance + 22 * pos(math.sin(t)) + 90 * pos(math.cos(t + 0.2)) ** 1.6
        return thigh, knee, 0.5 * (knee - thigh)

    near, far = leg(t), leg(t + math.pi)
    return {
        "lean": 13,
        "nod": -8,
        "thigh": (near[0], far[0]),
        "knee": (near[1], far[1]),
        "foot": (near[2], far[2]),
        "shoulder": (10 - 40 * math.sin(t), 10 + 40 * math.sin(t)),
        "elbow": (78 + 22 * pos(-math.sin(t)), 78 + 22 * pos(math.sin(t))),
        "air": flight(t, RUN_AIR),
    }


def side_angles(pose: str, phase: float) -> dict:
    if pose == "walking":
        return walk(phase)
    if pose == "running":
        return run(phase)
    if pose == "sitting":
        return sitting()
    if pose == "stairs":
        return stairs(phase)
    if pose == "ladder":
        return ladder_from_side(phase)
    return STAND


PLANTED = {"standing", "walking", "running", "sitting", "stairs"}


def posed(p: dict, pose: str, facing: str, phase: float = 0.0):
    """#329's `dolls.posed` with `rig.ts`'s run, sitting, stairs and ladder: every piece placed,
    its y from the ground, and whether to draw it mirrored. A ladder is climbed facing north."""
    if facing in ("north", "south"):
        view = "back" if facing == "north" else "front"
        a = ladder(phase % 1.0) if pose == "ladder" else port.STRAIGHT
        parts = port.place_straight(p, view, a)
        straight = port.place_straight(p, view, port.STRAIGHT)
        ground = port.lowest(p, parts if pose != "ladder" else straight)
    else:
        a = side_angles(pose, phase % 1.0)
        parts = port.place_side(p, a)
        ground = port.lowest(p, parts if pose in PLANTED else port.place_side(p, STAND))
        ground += a.get("air", 0.0) * UNIT
    for part in parts:
        part.y -= ground
    return parts, facing == "west"


def use() -> None:
    """Points #329's rig port at these poses."""
    port.posed = posed
