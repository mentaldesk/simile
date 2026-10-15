from collections.abc import Iterable

PALETTE: dict[str, str] = {
    "ink": "#181425",
    "night": "#262b44",
    "slate": "#3a4466",
    "steel": "#5a6988",
    "concrete": "#8b9bb4",
    "pavement": "#c0cbdc",
    "white": "#ffffff",
    "ice": "#a8e6f0",
    "cream": "#ead4aa",
    "peach": "#e8b796",
    "sand": "#e4a672",
    "tan": "#c28569",
    "brown": "#b86f50",
    "umber": "#733e39",
    "espresso": "#3e2731",
    "maroon": "#a22633",
    "red": "#e43b44",
    "orange": "#f77622",
    "amber": "#feae34",
    "yellow": "#fee761",
    "lime": "#63c74d",
    "green": "#3e8948",
    "forest": "#265c42",
    "deep": "#193c3e",
    "navy": "#124e89",
    "blue": "#0099db",
    "cyan": "#2ce8f5",
    "plum": "#68386c",
    "magenta": "#b55088",
    "pink": "#f6757a",
    "neon": "#ff4fa8",
    "violet": "#8a5cf6",
}

SHADE: dict[str, str] = {
    "ink": "ink",
    "night": "ink",
    "slate": "night",
    "steel": "slate",
    "concrete": "steel",
    "pavement": "concrete",
    "white": "pavement",
    "ice": "blue",
    "cream": "sand",
    "peach": "sand",
    "sand": "tan",
    "tan": "brown",
    "brown": "umber",
    "umber": "espresso",
    "espresso": "ink",
    "maroon": "espresso",
    "red": "maroon",
    "orange": "brown",
    "amber": "orange",
    "yellow": "amber",
    "lime": "green",
    "green": "forest",
    "forest": "deep",
    "deep": "ink",
    "navy": "night",
    "blue": "navy",
    "cyan": "blue",
    "plum": "espresso",
    "magenta": "plum",
    "pink": "red",
    "neon": "magenta",
    "violet": "plum",
}


def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


RGB: dict[str, tuple[int, int, int]] = {name: hex_to_rgb(value) for name, value in PALETTE.items()}


def rgba(name: str) -> tuple[int, int, int, int]:
    return (*RGB[name], 255)


def shade(name: str, steps: int = 1) -> str:
    for _ in range(steps):
        name = SHADE[name]
    return name


def _lab(rgb: tuple[int, int, int]) -> tuple[float, float, float]:
    def linear(c: int) -> float:
        v = c / 255
        return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (linear(c) for c in rgb)
    x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
    y = 0.2126 * r + 0.7152 * g + 0.0722 * b
    z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883

    def f(t: float) -> float:
        return t ** (1 / 3) if t > 0.008856 else 7.787 * t + 16 / 116

    fx, fy, fz = f(x), f(y), f(z)
    return 116 * fy - 16, 500 * (fx - fy), 200 * (fy - fz)


def nearest(rgb: tuple[int, int, int], choices: Iterable[str] = PALETTE) -> str:
    """The perceptually closest palette colour (CIE76 in Lab space)."""
    target = _lab(rgb)
    return min(
        choices,
        key=lambda name: sum((a - b) ** 2 for a, b in zip(_lab(RGB[name]), target, strict=True)),
    )
