import zlib
from dataclasses import dataclass
from typing import Any

from simile.art.canvas import Canvas
from simile.art.palette import PALETTE, hex_to_rgb, nearest, shade
from simile.schema import Appearance

FRAME_WIDTH = 16
FRAME_HEIGHT = 24
TOP_DOWN = ("down", "left", "right", "up")
THREE_QUARTER = ("down_left", "down_right", "up_left", "up_right")
DIRECTIONS = TOP_DOWN + THREE_QUARTER
MIRRORED = {"right": "left", "down_right": "down_left", "up_right": "up_left"}
FRAMES = 3

SKIN_TONES = ("cream", "peach", "sand", "tan", "brown", "umber")
CLOTH_COLOURS = tuple(name for name in PALETTE if name != "ink")
ACCENTS = ("amber", "cyan", "red", "lime", "violet", "neon")
LIGHT_COLOURS = {"white", "pavement", "ice", "cream", "peach", "yellow", "sand", "amber"}


def snap(hex_colour: str, choices: tuple[str, ...]) -> str:
    return nearest(hex_to_rgb(hex_colour), choices)


@dataclass(frozen=True)
class Colours:
    skin: str
    hair: str
    top: str
    bottom: str
    shoe: str
    accent: str
    apron: str

    @classmethod
    def of(cls, a: Appearance, seed: str | None = None) -> "Colours":
        top = snap(a.top_colour, CLOTH_COLOURS)
        bottom = snap(a.bottom_colour, CLOTH_COLOURS)
        hair = snap(a.hair_colour, CLOTH_COLOURS)
        free = [c for c in ACCENTS if c not in (top, bottom, hair)]
        accent = free[zlib.crc32(seed.encode()) % len(free)] if seed else free[0]
        return cls(
            skin=snap(a.skin, SKIN_TONES),
            hair=hair,
            top=top,
            bottom=bottom,
            shoe=snap(a.shoe_colour, CLOTH_COLOURS),
            accent=accent,
            apron="umber" if top in LIGHT_COLOURS else "cream",
        )

    def key(self) -> dict[str, str]:
        return {
            "s": self.skin,
            "S": shade(self.skin),
            "h": self.hair,
            "H": shade(self.hair),
            "t": self.top,
            "T": shade(self.top),
            "b": self.bottom,
            "B": shade(self.bottom),
            "f": self.shoe,
            "F": shade(self.shoe),
            "a": self.accent,
            "A": shade(self.accent),
            "p": self.apron,
            "P": shade(self.apron),
            "e": "ink",
            "w": "white",
            "k": "night",
            "g": "steel",
            "c": "cyan",
        }


FRONT_TORSO = {"slim": (4, 11), "average": (3, 12), "broad": (2, 13)}
QUARTER_TORSO = {"slim": (5, 11), "average": (4, 12), "broad": (3, 13)}
SIDE_TORSO = {"slim": (6, 9), "average": (5, 9), "broad": (5, 10)}

FRONT_HEAD = [
    "....ssssssss....",
    "...ssssssssssS..",
    "...ssssssssssS..",
    "...ssssssssssS..",
    "...ssssssssssS..",
    "...ssssssssssS..",
    "....sssssssSS...",
    ".....sssssSS....",
]
QUARTER_HEAD = [
    "....ssssssss....",
    "...ssssssssssS..",
    "...ssssssssssS..",
    "...ssssssssssS..",
    "..sssssssssssS..",
    "...ssssssssssS..",
    "...sssssssSS....",
    "....sssssS......",
]
SIDE_HEAD = [
    ".....ssssss.....",
    "....sssssssS....",
    "....sssssssS....",
    "....sssssssS....",
    "...ssssssssS....",
    "....sssssssS....",
    "....ssssssS.....",
    ".....sssSS......",
]
FRONT_LEGS = {
    1: [
        ".....bbbbbb.....",
        ".....bbbbbB.....",
        ".....bb..bB.....",
        ".....bb..bB.....",
        "....fff..fff....",
        "....FFF..FFF....",
    ],
    0: [
        "",
        ".....bbbbbb.....",
        "....fff..bB.....",
        "....FFF..bB.....",
        ".........fff....",
        ".........FFF....",
    ],
}
QUARTER_LEGS = {
    1: [
        ".....bbbbbb.....",
        ".....bbbbbB.....",
        ".....bb..bB.....",
        ".....bb..bB.....",
        "....fff.fff.....",
        "....FFF.FFF.....",
    ],
    0: [
        "",
        ".....bbbbbb.....",
        "...fff...bB.....",
        "...FFF...bB.....",
        "........fff.....",
        "........FFF.....",
    ],
    2: [
        "",
        ".....bbbbbb.....",
        ".....bB..fff....",
        ".....bB..FFF....",
        "....fff.........",
        "....FFF.........",
    ],
}
SIDE_LEGS = {
    1: [
        "......bbb.......",
        "......bbB.......",
        "......bbB.......",
        "......bbB.......",
        ".....ffff.......",
        ".....FFFF.......",
    ],
    0: [
        "",
        ".....nnnnn......",
        "....nnn..rr.....",
        "...nnn....rr....",
        "..fff......ff...",
        "..FFF......FF...",
    ],
}
SIDE_ARMS = {
    1: [
        ".......TT.......",
        ".......TT.......",
        ".......TT.......",
        ".......TT.......",
        ".......ss.......",
    ],
    0: [".......TT.......", ".......TT.......", "........TT......", ".........ss....."],
    2: [".......TT.......", "......TT........", ".....TT.........", ".....ss........."],
}


def _legs(direction: str, frame: int) -> list[str]:
    if direction in ("down_left", "up_left"):
        return QUARTER_LEGS[frame]
    if direction == "left":
        rows = SIDE_LEGS[1 if frame == 1 else 0]
        near, far = ("b", "B") if frame == 0 else ("B", "b")
        return [row.replace("n", near).replace("r", far) for row in rows]
    if frame == 2:
        return [row[::-1].replace("B", "b") for row in FRONT_LEGS[0]]
    return FRONT_LEGS[frame]


def _front_body(c: Canvas, build: str, frame: int, back: bool) -> None:
    left, right = FRONT_TORSO[build]
    c.rect(left + 1, 11, right - left - 1, 6, "t")
    c.vline(right - 1, 12, 5, "T")
    c.hline(left + 1, 16, right - left - 1, "T")
    if not back:
        c.px(7, 11, "s")
        c.px(8, 11, "s")
    for side, x in enumerate((left, right)):
        swing = 0 if frame == 1 else (-1 if (frame == 0) == (side == 0) else 1)
        c.vline(x, 12, 4 + swing, "T")
        c.px(x, 16 + swing, "s")
    c.stamp(FRONT_HEAD, {"s": "s", "S": "S"}, 0, 3)
    if not back:
        c.vline(5, 7, 2, "e")
        c.vline(10, 7, 2, "e")


def _quarter_body(c: Canvas, build: str, frame: int, back: bool) -> None:
    left, right = QUARTER_TORSO[build]
    c.rect(left + 1, 11, right - left - 1, 6, "t")
    c.vline(right - 1, 12, 5, "T")
    c.hline(left + 1, 16, right - left - 1, "T")
    if not back:
        c.px(6, 11, "s")
        c.px(7, 11, "s")
    for side, x in enumerate((left, right)):
        swing = 0 if frame == 1 else (-1 if (frame == 0) == (side == 0) else 1)
        c.vline(x, 12, 4 + swing, "T")
        c.px(x, 16 + swing, "s")
    c.stamp(QUARTER_HEAD, {"s": "s", "S": "S"}, 0, 3)
    if not back:
        c.vline(4, 7, 2, "e")
        c.vline(8, 7, 2, "e")


def _side_body(c: Canvas, build: str, frame: int) -> None:
    left, right = SIDE_TORSO[build]
    c.rect(left, 11, right - left + 1, 6, "t")
    c.vline(right, 12, 5, "T")
    c.hline(left, 16, right - left + 1, "T")
    c.stamp(SIDE_ARMS[frame], {"T": "T", "s": "s"}, 0, 12)
    c.stamp(SIDE_HEAD, {"s": "s", "S": "S"}, 0, 3)
    c.px(3, 7, "s")
    c.vline(5, 7, 2, "e")


HAIR: dict[str, dict[str, tuple[list[str], list[str]]]] = {
    "bald": {
        "down": ([], []),
        "up": ([], []),
        "left": ([], []),
        "down_left": ([], []),
        "up_left": ([], []),
    },
    "buzz": {
        "down": ([], ["", "", ".....HhhhhH.....", "...HhhhhhhhhH...", "...h........h..."]),
        "up": (
            [],
            [
                "",
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "...hhhhhhhhhH...",
                "...hhhhhhhhhH...",
                "...hhhhhhhhhH...",
                "...HhhhhhhhhH...",
                "....HHHHHHHH....",
            ],
        ),
        "left": (
            [],
            [
                "",
                "",
                "......hhhhh.....",
                "....hhhhhhhh....",
                "......hhhhhH....",
                "........hhhH....",
                ".........hhH....",
                ".........HH.....",
            ],
        ),
        "down_left": (
            [],
            [
                "",
                "",
                ".....hhhhhH.....",
                "...hhhhhhhhhH...",
                "...h.....hhhH...",
                "..........hhH...",
                "...........hH...",
            ],
        ),
        "up_left": (
            [],
            [
                "",
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "...hhhhhhhhhH...",
                "....hhhhhhhhH...",
                ".....hhhhhhhH...",
                ".....HhhhhhhH...",
                "......HHHHHH....",
            ],
        ),
    },
    "short": {
        "down": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhh.hhh.hhHH..",
                "..hh........HH..",
                "...h........H...",
            ],
        ),
        "up": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhH...",
                "...HhhhhhhhhH...",
                "....HHHHHHHH....",
            ],
        ),
        "left": (
            [],
            [
                "",
                "......hhhhh.....",
                "....hhhhhhhhh...",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhH..",
                "...h..hhhhhhHH..",
                "........hhhhH...",
                ".........hhhH...",
                ".........HHH....",
            ],
        ),
        "down_left": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hh.hhhhhhhHH..",
                "..h......hhhHH..",
                "..........hhH...",
                "...........H....",
            ],
        ),
        "up_left": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                ".....hhhhhhhH...",
                ".....HhhhhhhH...",
                "......HHHHHH....",
            ],
        ),
    },
    "curly": {
        "down": (
            [],
            [
                "",
                "...hhhhhhhhhh...",
                "..hhHhhHhhHhhh..",
                ".hhhhhhhhhhhhhH.",
                ".hhHhhHhhHhhHhH.",
                ".hhhhh.hhh.hhhH.",
                ".hHh........HhH.",
                ".hh..........hH.",
                "..H..........H..",
            ],
        ),
        "up": (
            [],
            [
                "",
                "...hhhhhhhhhh...",
                "..hhHhhHhhHhhh..",
                ".hhhhhhhhhhhhhH.",
                ".hhHhhHhhHhhHhH.",
                ".hhhhhhhhhhhhhH.",
                ".hHhhHhhHhhHhhH.",
                ".hhhhhhhhhhhhhH.",
                "..HhhHhhHhhHhH..",
                "...HHhHHhHHhH...",
            ],
        ),
        "left": (
            [],
            [
                "",
                "....hhhhhhhhh...",
                "...hhHhhHhhHhh..",
                "..hhhhhhhhhhhhH.",
                "..hHhhHhhHhhHhH.",
                "..hh..hhhhhhhhH.",
                "........hHhhHhH.",
                "........hhhhhhH.",
                ".........HhHhH..",
                "..........HHH...",
            ],
        ),
        "down_left": (
            [],
            [
                "",
                "...hhhhhhhhhh...",
                "..hhHhhHhhHhhh..",
                ".hhhhhhhhhhhhhH.",
                ".hhHhhHhhHhhHhH.",
                ".hhh.hhhhhhhhhH.",
                ".hH......hHhhhH.",
                ".h........hhhhH.",
                "..........HhHH..",
                "...........HH...",
            ],
        ),
        "up_left": (
            [],
            [
                "",
                "...hhhhhhhhhh...",
                "..hhHhhHhhHhhh..",
                ".hhhhhhhhhhhhhH.",
                ".hhHhhHhhHhhHhH.",
                ".hhhhhhhhhhhhhH.",
                ".hhhhHhhHhhHhhH.",
                "....hhhhhhhhhhH.",
                ".....HhhHhhHhH..",
                "......HHhHHhH...",
            ],
        ),
    },
    "bob": {
        "down": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhHH..",
                "..hh........HH..",
                "..hh........HH..",
                "..hh........HH..",
                "..hh........HH..",
                "..HH........HH..",
            ],
        ),
        "up": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..HHHHHHHHHHHH..",
            ],
        ),
        "left": (
            [],
            [
                "",
                "......hhhhh.....",
                "....hhhhhhhhh...",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                ".......hhhhhhH..",
                ".......hhhhhhH..",
                ".......hhhhhhH..",
                ".......hhhhhhH..",
                ".......HHHHHHH..",
            ],
        ),
        "down_left": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhHH..",
                "..h.......hhHH..",
                "..h.......hhHH..",
                "..h.......hhHH..",
                "..h.......hhHH..",
                "..H.......HHHH..",
            ],
        ),
        "up_left": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                "....hhhhhhhhhH..",
                "....hhhhhhhhhH..",
                "....hhhhhhhhhH..",
                "....HHHHHHHHHH..",
            ],
        ),
    },
    "long": {
        "down": (
            [
                "",
                "",
                "",
                "",
                "",
                "",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhh..",
                "..HHHHHHHHHHHH..",
            ],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhh.hhhhHH..",
                "..hh........HH..",
                "..hh........HH..",
                "..hh........HH..",
                "..hh........HH..",
                "..hh........HH..",
                "..h..........H..",
                "..h..........H..",
                "..H..........H..",
            ],
        ),
        "up": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhH...",
                "...HHHHHHHHHH...",
            ],
        ),
        "left": (
            [],
            [
                "",
                "......hhhhh.....",
                "....hhhhhhhhh...",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhH..",
                "...hh.hhhhhhhH..",
                "........hhhhhH..",
                "........hhhhhH..",
                ".........hhhhH..",
                ".........hhhhH..",
                ".........hhhhH..",
                "..........hhhH..",
                "..........hhhH..",
                "..........HHH...",
            ],
        ),
        "down_left": (
            [
                "",
                "",
                "",
                "",
                "",
                "",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhh..",
                "...HHHHHHHHHHH..",
            ],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhh.hhhhhHH..",
                "..h.......hhHH..",
                "..h.......hhHH..",
                "..h.......hhHH..",
                "..h.......hhHH..",
                "..h........hHH..",
                "...........hhH..",
                "...........hhH..",
                "...........HH...",
            ],
        ),
        "up_left": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                "....hhhhhhhhhH..",
                "....hhhhhhhhhH..",
                "....hhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                "...hhhhhhhhhH...",
                "...HHHHHHHHHH...",
            ],
        ),
    },
    "ponytail": {
        "down": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhHH.",
                "..hh........HHH.",
                "..h..........HH.",
                ".............HH.",
                ".............H..",
            ],
        ),
        "up": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhH...",
                "...HhhhaahhhH...",
                "....HHhhhHHH....",
                "......hhH.......",
                "......hhH.......",
                "......hhH.......",
                ".......H........",
            ],
        ),
        "left": (
            [],
            [
                "",
                "......hhhhh.....",
                "....hhhhhhhhh...",
                "...hhhhhhhhhhh..",
                "...hhhhhhhhhhH..",
                "...h....hhhhhaH.",
                "........hhhhhhH.",
                ".........hhhHhH.",
                ".........HHH.hH.",
                ".............hH.",
                "............hH..",
                "............H...",
            ],
        ),
        "down_left": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhHH.",
                "..h......hhhHaH.",
                "..........hhhhH.",
                "...........hhhH.",
                ".............hH.",
                ".............hH.",
                "............hH..",
                "............H...",
            ],
        ),
        "up_left": (
            [],
            [
                "",
                ".....hhhhhh.....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                ".....hhhhhhhH...",
                ".....HhhaahhH...",
                "......HhhhHH....",
                ".......hhH......",
                ".......hhH......",
                ".......hhH......",
                "........H.......",
            ],
        ),
    },
    "bun": {
        "down": (
            [],
            [
                "",
                ".....hhhhhH.....",
                "....HhhhhhhH....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hh........HH..",
                "...h........H...",
            ],
        ),
        "up": (
            [],
            [
                "",
                ".....hhhhhH.....",
                "....HhhhhhHH....",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhH...",
                "...HhhhhhhhhH...",
                "....HHHHHHHH....",
            ],
        ),
        "left": (
            [],
            [
                "",
                "........hhhhH...",
                "......hhhhhHH...",
                "....hhhhhhhhhh..",
                "...hhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                "...h...hhhhhhH..",
                "........hhhhH...",
                ".........hhhH...",
                ".........HHH....",
            ],
        ),
        "down_left": (
            [],
            [
                "",
                ".......hhhhH....",
                ".....hhhhhhHH...",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhH..",
                "..hhhhhhhhhhhH..",
                "..h......hhhHH..",
                "..........hhH...",
                "...........H....",
            ],
        ),
        "up_left": (
            [],
            [
                "",
                "......hhhhhH....",
                ".....HhhhhhHH...",
                "...hhhhhhhhhh...",
                "..hhhhhhhhhhhh..",
                "..hhhhhhhhhhhH..",
                "...hhhhhhhhhhH..",
                ".....hhhhhhhhH..",
                ".....hhhhhhhH...",
                ".....HhhhhhhH...",
                "......HHHHHH....",
            ],
        ),
    },
}

ACCESSORY_ART: dict[str, dict[str, list[str]]] = {
    "glasses": {
        "down": ["", "", "", "", "", "", "....ggg..ggg....", "....g.gggg.g...."],
        "left": ["", "", "", "", "", "", "...ggg..........", "...g.gggggg....."],
        "up": [],
        "down_left": ["", "", "", "", "", "", "...ggg.ggg......", "...g.ggg.ggg...."],
        "up_left": [],
    },
    "sunglasses": {
        "down": ["", "", "", "", "", "", "", "....eeeeeeee....", "....eke..eke...."],
        "left": ["", "", "", "", "", "", "", "...eeeeeee......", "...eke..........."],
        "up": [],
        "down_left": ["", "", "", "", "", "", "", "...eeeeeeeee....", "...eke.eke......"],
        "up_left": [],
    },
    "cap": {
        "down": [
            "",
            ".....aaaaaa.....",
            "....aaaaaaaa....",
            "...aaawwaaaaA...",
            "...aaaaaaaaaA...",
            "..AAAAAAAAAAAA..",
        ],
        "up": [
            "",
            ".....aaaaaa.....",
            "....aaaaaaaa....",
            "...aaaaaaaaaA...",
            "...aaaaaaaaaA...",
            "...AAAaaaaAAA...",
            "......AAAA......",
        ],
        "left": [
            "",
            "......aaaaa.....",
            ".....aaaaaaaa...",
            "....awwaaaaaaA..",
            "....aaaaaaaaaA..",
            ".AAAAAAAAAAAAA..",
        ],
        "down_left": [
            "",
            ".....aaaaaa.....",
            "....aaaaaaaa....",
            "...aawwaaaaaA...",
            "...aaaaaaaaaA...",
            ".AAAAAAAAAAAA...",
            "..AAAA..........",
        ],
        "up_left": [
            "",
            ".....aaaaaa.....",
            "....aaaaaaaa....",
            "...aaaaaaaaaA...",
            "...aaaaaaaaaA...",
            ".AAAAAaaaaAAA...",
            ".......AAAA.....",
        ],
    },
    "beanie": {
        "down": [
            "",
            "....aaaaaaaa....",
            "...aAaAaAaAaA...",
            "...aaaaaaaaaa...",
            "..AaAaAaAaAaAA..",
            "..AAAAAAAAAAAA..",
        ],
        "up": [
            "",
            "....aaaaaaaa....",
            "...aAaAaAaAaA...",
            "...aaaaaaaaaa...",
            "..AaAaAaAaAaAA..",
            "..AAAAAAAAAAAA..",
        ],
        "left": [
            "",
            ".....aaaaaaaa...",
            "....aAaAaAaAaA..",
            "....aaaaaaaaaa..",
            "...AaAaAaAaAaA..",
            "...AAAAAAAAAAA..",
        ],
        "down_left": [
            "",
            "....aaaaaaaa....",
            "...aAaAaAaAaA...",
            "...aaaaaaaaaa...",
            "..AaAaAaAaAaAA..",
            "..AAAAAAAAAAAA..",
        ],
        "up_left": [
            "",
            "....aaaaaaaa....",
            "...aAaAaAaAaA...",
            "...aaaaaaaaaa...",
            "..AaAaAaAaAaAA..",
            "..AAAAAAAAAAAA..",
        ],
    },
    "headphones": {
        "down": [
            "",
            "....kkkkkkkk....",
            "...k........k...",
            "..k..........k..",
            "..k..........k..",
            ".kk..........kk.",
            ".kc..........ck.",
            ".kk..........kk.",
        ],
        "up": [
            "",
            "....kkkkkkkk....",
            "...k........k...",
            "..k..........k..",
            "..k..........k..",
            ".kk..........kk.",
            ".kc..........ck.",
            ".kk..........kk.",
        ],
        "left": [
            "",
            "......kkkk......",
            ".....k....k.....",
            "..........k.....",
            "..........k.....",
            ".........kkk....",
            ".........kck....",
            ".........kkk....",
        ],
        "down_left": [
            "",
            "....kkkkkkkk....",
            "...k........k...",
            "............k...",
            "............k...",
            "...........kkk..",
            "...........kck..",
            "...........kkk..",
        ],
        "up_left": [
            "",
            "....kkkkkkkk....",
            "...k........k...",
            "...k............",
            "...k............",
            "..kkk...........",
            "..kck...........",
            "..kkk...........",
        ],
    },
    "scarf": {
        "down": [
            *[""] * 10,
            "...aaaaaaaaaa...",
            "....AaaaaaaA....",
            "........aA......",
            "........aA......",
        ],
        "up": [*[""] * 10, "...aaaaaaaaaa...", "....AAAAAAAA...."],
        "left": [
            *[""] * 10,
            "....aaaaaaa.....",
            ".....AaaaaA.....",
            ".........aA.....",
            ".........aA.....",
        ],
        "down_left": [
            *[""] * 10,
            "...aaaaaaaaaa...",
            "....AaaaaaaA....",
            "......aA........",
            "......aA........",
        ],
        "up_left": [*[""] * 10, "...aaaaaaaaaa...", "....AAAAAAAA...."],
    },
    "apron": {
        "down": [
            *[""] * 11,
            "......P..P......",
            "......pppp......",
            "......pppp......",
            ".....pppppp.....",
            ".....pppppP.....",
            ".....PPPPPP.....",
        ],
        "up": [*[""] * 14, "....pppPPppp....", ".......PP.......", "......P..P......"],
        "left": [*[""] * 12, "....p...", "....p...", "...pp...", "...pP...", "...PP..."],
        "down_left": [
            *[""] * 11,
            ".....P..P.......",
            ".....pppp.......",
            ".....pppp.......",
            "....pppppp......",
            "....pppppP......",
            "....PPPPPP......",
        ],
        "up_left": [*[""] * 14, ".....ppPPppp....", "........PP......", ".......P..P....."],
    },
    "backpack": {
        "down": [
            *[""] * 11,
            ".....A....A.....",
            ".....A....A.....",
            ".....A....A.....",
            ".....A....A.....",
        ],
        "up": [
            *[""] * 11,
            "....AaaaaaaA....",
            "....aaaaaaaa....",
            "....aAAAAAAa....",
            "....aaaaaaaa....",
            "....aaaaaaaa....",
            "....aaaaaaaA....",
            "....AAAAAAAA....",
        ],
        "left": [],
        "down_left": [
            *[""] * 11,
            "....A....A......",
            "....A....A......",
            "....A....A......",
            "....A....A......",
        ],
        "up_left": [
            *[""] * 11,
            ".....AaaaaaaA...",
            ".....aaaaaaaaA..",
            ".....aAAAAAAaA..",
            ".....aaaaaaaaA..",
            ".....aaaaaaaaA..",
            ".....aaaaaaaAA..",
            ".....AAAAAAAA...",
        ],
    },
}
BACKPACK_BEHIND = {
    "left": [
        *[""] * 11,
        "..........AaA...",
        "..........aaaA..",
        "..........aaaA..",
        "..........aaaA..",
        "..........aaaA..",
        "..........AAAA..",
    ],
    "down_left": [
        *[""] * 11,
        "...........aaA..",
        "...........aaaA.",
        "...........aaaA.",
        "...........aaaA.",
        "...........aaaA.",
        "...........AAA..",
    ],
}


def _body(c: Canvas, direction: str, build: str, frame: int) -> None:
    if direction == "left":
        _side_body(c, build, frame)
    elif direction in ("down_left", "up_left"):
        _quarter_body(c, build, frame, back=direction == "up_left")
    else:
        _front_body(c, build, frame, back=direction == "up")


def draw_frame(
    appearance: Appearance, direction: str, frame: int, seed: str | None = None
) -> Canvas:
    if direction in MIRRORED:
        return draw_frame(appearance, MIRRORED[direction], frame, seed).flipped()
    key = Colours.of(appearance, seed).key()
    accessories = set(appearance.accessories)
    behind, front = HAIR[appearance.hair_style][direction]
    if accessories & {"cap", "beanie"} and appearance.hair_style in ("bun", "curly"):
        front = [row if i > 4 else "" for i, row in enumerate(front)]

    upper = Canvas(FRAME_WIDTH, FRAME_HEIGHT)
    if "backpack" in accessories and direction in BACKPACK_BEHIND:
        upper.stamp(BACKPACK_BEHIND[direction], key)
    upper.stamp(behind, key)
    body = Canvas(FRAME_WIDTH, FRAME_HEIGHT)
    _body(body, direction, appearance.build, frame)
    body.recolour(key)
    upper.paste(body)
    for name in ("apron", "scarf", "backpack"):
        if name in accessories:
            upper.stamp(ACCESSORY_ART[name][direction], key)
    upper.stamp(front, key)
    for name in ("cap", "beanie", "headphones", "glasses", "sunglasses"):
        if name in accessories:
            upper.stamp(ACCESSORY_ART[name][direction], key)

    c = Canvas(FRAME_WIDTH, FRAME_HEIGHT)
    c.stamp(_legs(direction, frame), key, 0, 17)
    c.paste(upper, 0, 0 if frame == 1 else 1)
    return c.outlined("ink")


def sprite_sheet(appearance: Appearance, seed: str | None = None) -> Canvas:
    sheet = Canvas(FRAME_WIDTH * FRAMES, FRAME_HEIGHT * len(DIRECTIONS))
    for row, direction in enumerate(DIRECTIONS):
        for col in range(FRAMES):
            sheet.paste(
                draw_frame(appearance, direction, col, seed), col * FRAME_WIDTH, row * FRAME_HEIGHT
            )
    return sheet


def frame_name(direction: str, frame: int) -> str:
    return f"{direction}-{frame}"


def atlas(image: str) -> dict[str, Any]:
    frames = {}
    for row, direction in enumerate(DIRECTIONS):
        for col in range(FRAMES):
            rect = {
                "x": col * FRAME_WIDTH,
                "y": row * FRAME_HEIGHT,
                "w": FRAME_WIDTH,
                "h": FRAME_HEIGHT,
            }
            frames[frame_name(direction, col)] = {
                "frame": rect,
                "rotated": False,
                "trimmed": False,
                "spriteSourceSize": {"x": 0, "y": 0, "w": FRAME_WIDTH, "h": FRAME_HEIGHT},
                "sourceSize": {"w": FRAME_WIDTH, "h": FRAME_HEIGHT},
            }
    return {
        "frames": frames,
        "meta": {
            "image": image,
            "format": "RGBA8888",
            "size": {"w": FRAME_WIDTH * FRAMES, "h": FRAME_HEIGHT * len(DIRECTIONS)},
            "scale": "1",
        },
    }


def _look(
    skin: str,
    hair_style: str,
    hair: str,
    top: str,
    bottom: str,
    shoes: str,
    build: str,
    *accessories: str,
) -> Appearance:
    return Appearance.model_validate(
        {
            "skin": skin,
            "hair_style": hair_style,
            "hair_colour": hair,
            "top_colour": top,
            "bottom_colour": bottom,
            "shoe_colour": shoes,
            "build": build,
            "accessories": list(accessories),
        }
    )


PLAYER = _look(
    "#e4a672", "short", "#3e2731", "#0099db", "#3a4466", "#ffffff", "average", "backpack"
)

SAMPLES: dict[str, Appearance] = {
    "sample_barista": _look(
        "#e8b98f", "bob", "#1c1b22", "#d9645a", "#2f3e5c", "#f2efe6", "slim", "apron"
    ),
    "sample_coder": _look(
        "#c28569",
        "buzz",
        "#262b44",
        "#5a6988",
        "#262b44",
        "#e43b44",
        "average",
        "headphones",
        "glasses",
    ),
    "sample_student": _look(
        "#ead4aa", "ponytail", "#733e39", "#f6757a", "#124e89", "#ffffff", "slim", "backpack"
    ),
    "sample_courier": _look(
        "#b86f50", "short", "#181425", "#feae34", "#3a4466", "#3a4466", "broad", "cap"
    ),
    "sample_artist": _look(
        "#e4a672", "curly", "#ff4fa8", "#68386c", "#3e8948", "#fee761", "average", "scarf"
    ),
    "sample_elder": _look(
        "#e8b796", "bald", "#c0cbdc", "#8b9bb4", "#3e2731", "#3e2731", "broad", "glasses"
    ),
    "sample_runner": _look(
        "#733e39", "long", "#181425", "#2ce8f5", "#262b44", "#63c74d", "slim", "sunglasses"
    ),
    "sample_skater": _look(
        "#c28569", "short", "#feae34", "#e43b44", "#5a6988", "#181425", "average", "beanie"
    ),
    "sample_teacher": _look(
        "#3e2731", "bun", "#181425", "#265c42", "#ead4aa", "#733e39", "average", "glasses"
    ),
    "sample_gardener": _look(
        "#e4a672", "curly", "#c0cbdc", "#3e8948", "#733e39", "#733e39", "broad", "cap", "scarf"
    ),
}
