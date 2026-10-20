"""Colour maths for the dolls: sRGB, OKLab for muting, and CIELAB for CIEDE2000 distances."""

import numpy as np
from numpy.typing import ArrayLike, NDArray

RGB = tuple[int, int, int]

KNEE = 0.07
KEEP = 0.6
"""Chroma above `KNEE` (OKLCH) is kept at `KEEP`, so loud colours sit in the muted card world."""

_TO_LMS = np.array(
    [
        [0.4122214708, 0.5363325363, 0.0514459929],
        [0.2119034982, 0.6806995451, 0.1073969566],
        [0.0883024619, 0.2817188376, 0.6299787005],
    ]
)
_TO_OKLAB = np.array(
    [
        [0.2104542553, 0.7936177850, -0.0040720468],
        [1.9779984951, -2.4285922050, 0.4505937099],
        [0.0259040371, 0.7827717662, -0.8086757660],
    ]
)
_TO_XYZ = np.array(
    [
        [0.4124564, 0.3575761, 0.1804375],
        [0.2126729, 0.7151522, 0.0721750],
        [0.0193339, 0.1191920, 0.9503041],
    ]
)
_WHITE = np.array([0.95047, 1.0, 1.08883])


def rgb(hex_colour: str) -> RGB:
    h = hex_colour.lstrip("#")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def hex_of(colour: ArrayLike) -> str:
    r, g, b = (int(round(float(v))) for v in np.asarray(colour).reshape(3))
    return f"#{r:02x}{g:02x}{b:02x}"


def mix(a: RGB, b: RGB, t: float) -> RGB:
    return (
        round(a[0] + (b[0] - a[0]) * t),
        round(a[1] + (b[1] - a[1]) * t),
        round(a[2] + (b[2] - a[2]) * t),
    )


def darker(c: RGB, f: float = 0.78) -> RGB:
    return round(c[0] * f), round(c[1] * f), round(c[2] * f)


def lighter(c: RGB, t: float = 0.25) -> RGB:
    return mix(c, (255, 255, 255), t)


def luminance(c: RGB) -> float:
    return (0.299 * c[0] + 0.587 * c[1] + 0.114 * c[2]) / 255


def _linear(colours: ArrayLike) -> NDArray[np.float64]:
    c = np.asarray(colours, dtype=np.float64) / 255
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def _encoded(linear: NDArray[np.float64]) -> NDArray[np.float64]:
    c = np.clip(linear, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055) * 255


def oklab(colours: ArrayLike) -> NDArray[np.float64]:
    return np.cbrt(_linear(colours) @ _TO_LMS.T) @ _TO_OKLAB.T


def from_oklab(lab: ArrayLike) -> NDArray[np.float64]:
    lms = np.asarray(lab, dtype=np.float64) @ np.linalg.inv(_TO_OKLAB).T
    return _encoded((lms**3) @ np.linalg.inv(_TO_LMS).T)


def muted(colour: RGB) -> RGB:
    """`colour` with its chroma above the knee softened, keeping its lightness and hue."""
    lab = oklab(colour)
    chroma = float(np.hypot(lab[1], lab[2]))
    if chroma <= KNEE:
        return colour
    lab[1:] *= (KNEE + (chroma - KNEE) * KEEP) / chroma
    r, g, b = (int(round(float(v))) for v in from_oklab(lab))
    return r, g, b


def cielab(colours: ArrayLike) -> NDArray[np.float64]:
    xyz = (_linear(colours) @ _TO_XYZ.T) / _WHITE
    f = np.where(xyz > 216 / 24389, np.cbrt(xyz), (24389 / 27 * xyz + 16) / 116)
    return np.stack(
        [116 * f[..., 1] - 16, 500 * (f[..., 0] - f[..., 1]), 200 * (f[..., 1] - f[..., 2])],
        axis=-1,
    )


def delta_e(a: ArrayLike, b: ArrayLike) -> NDArray[np.float64]:
    """CIEDE2000 between sRGB colours: about 2 is just noticeable, 10 a clear difference."""
    return delta_e_lab(cielab(a), cielab(b))


def delta_e_lab(lab_a: ArrayLike, lab_b: ArrayLike) -> NDArray[np.float64]:
    l1, a1, b1 = np.moveaxis(np.asarray(lab_a, dtype=np.float64), -1, 0)
    l2, a2, b2 = np.moveaxis(np.asarray(lab_b, dtype=np.float64), -1, 0)
    c_mean = (np.hypot(a1, b1) + np.hypot(a2, b2)) / 2
    g = 0.5 * (1 - np.sqrt(c_mean**7 / (c_mean**7 + 25.0**7)))
    a1p, a2p = (1 + g) * a1, (1 + g) * a2
    c1p, c2p = np.hypot(a1p, b1), np.hypot(a2p, b2)
    h1p = np.degrees(np.arctan2(b1, a1p)) % 360
    h2p = np.degrees(np.arctan2(b2, a2p)) % 360
    grey = c1p * c2p == 0
    dh = h2p - h1p
    dh = np.where(dh > 180, dh - 360, np.where(dh < -180, dh + 360, dh))
    dh = np.where(grey, 0, dh)
    d_hue = 2 * np.sqrt(c1p * c2p) * np.sin(np.radians(dh / 2))
    l_mean, cp_mean = (l1 + l2) / 2, (c1p + c2p) / 2
    total = h1p + h2p
    h_mean = np.where(
        np.abs(h1p - h2p) > 180, np.where(total < 360, total + 360, total - 360) / 2, total / 2
    )
    h_mean = np.where(grey, total, h_mean)
    t = (
        1
        - 0.17 * np.cos(np.radians(h_mean - 30))
        + 0.24 * np.cos(np.radians(2 * h_mean))
        + 0.32 * np.cos(np.radians(3 * h_mean + 6))
        - 0.20 * np.cos(np.radians(4 * h_mean - 63))
    )
    rotation = 30 * np.exp(-(((h_mean - 275) / 25) ** 2))
    rc = 2 * np.sqrt(cp_mean**7 / (cp_mean**7 + 25.0**7))
    sl = 1 + 0.015 * (l_mean - 50) ** 2 / np.sqrt(20 + (l_mean - 50) ** 2)
    sc = 1 + 0.045 * cp_mean
    sh = 1 + 0.015 * cp_mean * t
    rt = -np.sin(np.radians(2 * rotation)) * rc
    dl, dc, dhh = (l2 - l1) / sl, (c2p - c1p) / sc, d_hue / sh
    return np.sqrt(dl**2 + dc**2 + dhh**2 + rt * dc * dhh)
