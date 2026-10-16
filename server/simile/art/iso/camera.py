"""The camera every iso render shares. Standard library only, for Blender's Python too."""

import math

TILE_W = 96
TILE_H = 48
TILE_M = 1.1
ELEVATION = 30.0
PX_PER_M = TILE_W / (TILE_M * math.sqrt(2))
UPRIGHT_PX_PER_M = PX_PER_M * math.cos(math.radians(ELEVATION))

_S = math.sqrt(0.5)
_SIN, _COS = math.sin(math.radians(ELEVATION)), math.cos(math.radians(ELEVATION))
ROTATION = (math.radians(90 - ELEVATION), 0.0, math.radians(45))
RIGHT = (_S, _S, 0.0)
UP = (-_S * _SIN, _S * _SIN, _COS)
FORWARD = (-_S * _COS, _S * _COS, -_SIN)


def project(x: float, y: float, z: float = 0.0) -> tuple[float, float]:
    """Screen px of a map point (x, y in tiles, z in metres), with tile (0, 0) at the origin."""
    return (x - y) * TILE_W / 2, (x + y) * TILE_H / 2 - z * UPRIGHT_PX_PER_M


def unproject(sx: float, sy: float) -> tuple[float, float]:
    """The map point on the ground (z = 0) at a screen position."""
    d, s = sx / (TILE_W / 2), sy / (TILE_H / 2)
    return (s + d) / 2, (s - d) / 2


def world(x: float, y: float, z: float = 0.0) -> tuple[float, float, float]:
    """Blender's coordinates for a map point: metres, x east, y north, z up."""
    return x * TILE_M, -y * TILE_M, z


def screen(p: tuple[float, float, float]) -> tuple[float, float]:
    """Screen px of a point in Blender's coordinates; the inverse direction of `world`."""
    right = sum(a * b for a, b in zip(p, RIGHT, strict=True))
    up = sum(a * b for a, b in zip(p, UP, strict=True))
    return right * PX_PER_M, -up * PX_PER_M
