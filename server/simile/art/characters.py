from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from simile.art.canvas import Canvas
from simile.art.palette import PALETTE, hex_to_rgb, nearest, shade

FRAME_WIDTH = 16
FRAME_HEIGHT = 24
DIRECTIONS = ("down", "left", "right", "up")
FRAMES = 3
HAIR_STYLES = ("bald", "buzz", "short", "curly", "bob", "long", "ponytail", "bun")
BUILDS = ("slim", "average", "broad")
ACCESSORIES = (
    "glasses",
    "sunglasses",
    "cap",
    "beanie",
    "headphones",
    "scarf",
    "backpack",
    "apron",
)

SKIN_TONES = ("cream", "peach", "sand", "tan", "brown", "umber")
CLOTH_COLOURS = tuple(name for name in PALETTE if name != "ink")
ACCENTS = ("amber", "cyan", "red", "lime", "violet", "neon")
LIGHT_COLOURS = {"white", "pavement", "ice", "cream", "peach", "yellow", "sand", "amber"}


@dataclass(frozen=True)
class Appearance:
    """Mirrors F2's Appearance: colours are #rrggbb, snapped to the palette when drawn."""

    skin: str
    hair_style: str
    hair_colour: str
    top_colour: str
    bottom_colour: str
    shoe_colour: str
    build: str
    accessories: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.hair_style not in HAIR_STYLES:
            raise ValueError(f"unknown hair style {self.hair_style!r}")
        if self.build not in BUILDS:
            raise ValueError(f"unknown build {self.build!r}")
        for accessory in self.accessories:
            if accessory not in ACCESSORIES:
                raise ValueError(f"unknown accessory {accessory!r}")
        for colour in (
            self.skin,
            self.hair_colour,
            self.top_colour,
            self.bottom_colour,
            self.shoe_colour,
        ):
            hex_to_rgb(colour)

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> "Appearance":
        return cls(
            skin=data["skin"],
            hair_style=data["hair_style"],
            hair_colour=data["hair_colour"],
            top_colour=data["top_colour"],
            bottom_colour=data["bottom_colour"],
            shoe_colour=data["shoe_colour"],
            build=data["build"],
            accessories=tuple(data.get("accessories", ())),
        )


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
    def of(cls, a: Appearance) -> "Colours":
        top = snap(a.top_colour, CLOTH_COLOURS)
        bottom = snap(a.bottom_colour, CLOTH_COLOURS)
        hair = snap(a.hair_colour, CLOTH_COLOURS)
        accent = next(c for c in ACCENTS if c not in (top, bottom, hair))
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
    1: [".......TT.......", ".......TT.......", ".......TT.......", ".......TT.......", ".......ss......."],
    0: [".......TT.......", ".......TT.......", "........TT......", ".........ss....."],
    2: [".......TT.......", "......TT........", ".....TT.........", ".....ss........."],
}


def _legs(direction: str, frame: int) -> list[str]:
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


def _side_body(c: Canvas, build: str, frame: int) -> None:
    left, right = SIDE_TORSO[build]
    c.rect(left, 11, right - left + 1, 6, "t")
    c.vline(right, 12, 5, "T")
    c.hline(left, 16, right - left + 1, "T")
    c.stamp(SIDE_ARMS[frame], {"T": "T", "s": "s"}, 0, 12)
    c.stamp(SIDE_HEAD, {"s": "s", "S": "S"}, 0, 3)
    c.px(3, 7, "s")
    c.vline(5, 7, 2, "e")


# Hair: (behind body, in front) per view. Rows start at y=0.
HAIR: dict[str, dict[str, tuple[list[str], list[str]]]] = {
    "bald": {"down": ([], []), "up": ([], []), "left": ([], [])},
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
    },
    "curly": {
        "down": (
            [],
            [
                "....h.hh.h.h....",
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
                "....h.hh.h.h....",
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
                ".....h.hh.h.....",
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
                "........hhhhhhhH",
                ".........hhhH.hH",
                ".........HHH..hH",
                "..............hH",
                ".............hH.",
                ".............H..",
            ],
        ),
    },
    "bun": {
        "down": (
            [],
            [
                "......hhhh......",
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
                "......hhhh......",
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
                ".........hhh....",
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
    },
}

ACCESSORY_ART: dict[str, dict[str, list[str]]] = {
    "glasses": {
        "down": ["", "", "", "", "", "", "....ggg..ggg....", "....g.gggg.g...."],
        "left": ["", "", "", "", "", "", "...ggg..........", "...g.gggggg....."],
        "up": [],
    },
    "sunglasses": {
        "down": ["", "", "", "", "", "", "", "....eeeeeeee....", "....eke..eke...."],
        "left": ["", "", "", "", "", "", "", "...eeeeeee......", "...eke..........."],
        "up": [],
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
            "AAAAAAAAAAAAAA..",
        ],
    },
    "beanie": {
        "down": [
            "......aaaa......",
            "....aaaaaaaa....",
            "...aAaAaAaAaA...",
            "...aaaaaaaaaa...",
            "..AaAaAaAaAaAA..",
            "..AAAAAAAAAAAA..",
        ],
        "up": [
            "......aaaa......",
            "....aaaaaaaa....",
            "...aAaAaAaAaA...",
            "...aaaaaaaaaa...",
            "..AaAaAaAaAaAA..",
            "..AAAAAAAAAAAA..",
        ],
        "left": [
            "......aaaa......",
            ".....aaaaaaaa...",
            "....aAaAaAaAaA..",
            "....aaaaaaaaaa..",
            "...AaAaAaAaAaA..",
            "...AAAAAAAAAAA..",
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
    },
    "scarf": {
        "down": [*[""] * 10, "...aaaaaaaaaa...", "....AaaaaaaA....", "........aA......", "........aA......"],
        "up": [*[""] * 10, "...aaaaaaaaaa...", "....AAAAAAAA...."],
        "left": [*[""] * 10, "....aaaaaaa.....", ".....AaaaaA.....", ".........aA.....", ".........aA....."],
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
    },
    "backpack": {
        "down": [*[""] * 11, ".....A....A.....", ".....A....A.....", ".....A....A.....", ".....A....A....."],
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
        "left": [
            *[""] * 11,
            "..........AaA...",
            "..........aaaA..",
            "..........aaaA..",
            "..........aaaA..",
            "..........aaaA..",
            "..........AAAA..",
        ],
    },
}


def draw_frame(appearance: Appearance, direction: str, frame: int) -> Canvas:
    if direction == "right":
        return draw_frame(appearance, "left", frame).flipped()
    key = Colours.of(appearance).key()
    accessories = set(appearance.accessories)
    behind, front = HAIR[appearance.hair_style][direction]
    if accessories & {"cap", "beanie"} and appearance.hair_style in ("bun", "curly"):
        front = [row if i > 4 else "" for i, row in enumerate(front)]

    upper = Canvas(FRAME_WIDTH, FRAME_HEIGHT)
    if direction == "left" and "backpack" in accessories:
        upper.stamp(ACCESSORY_ART["backpack"]["left"], key)
    upper.stamp(behind, key)
    body = Canvas(FRAME_WIDTH, FRAME_HEIGHT)
    if direction == "left":
        _side_body(body, appearance.build, frame)
    else:
        _front_body(body, appearance.build, frame, back=direction == "up")
    body.recolour(key)
    upper.paste(body)
    for name in ("apron", "scarf"):
        if name in accessories:
            upper.stamp(ACCESSORY_ART[name][direction], key)
    if "backpack" in accessories and direction != "left":
        upper.stamp(ACCESSORY_ART["backpack"][direction], key)
    upper.stamp(front, key)
    for name in ("cap", "beanie", "headphones", "glasses", "sunglasses"):
        if name in accessories:
            upper.stamp(ACCESSORY_ART[name][direction], key)

    c = Canvas(FRAME_WIDTH, FRAME_HEIGHT)
    c.stamp(_legs(direction, frame), key, 0, 17)
    c.paste(upper, 0, 0 if frame == 1 else 1)
    return c.outlined("ink")


def sprite_sheet(appearance: Appearance) -> Canvas:
    sheet = Canvas(FRAME_WIDTH * FRAMES, FRAME_HEIGHT * len(DIRECTIONS))
    for row, direction in enumerate(DIRECTIONS):
        for col in range(FRAMES):
            sheet.paste(draw_frame(appearance, direction, col), col * FRAME_WIDTH, row * FRAME_HEIGHT)
    return sheet


def frame_name(direction: str, frame: int) -> str:
    return f"{direction}-{frame}"


def atlas(image: str) -> dict[str, Any]:
    frames = {}
    for row, direction in enumerate(DIRECTIONS):
        for col in range(FRAMES):
            rect = {"x": col * FRAME_WIDTH, "y": row * FRAME_HEIGHT, "w": FRAME_WIDTH, "h": FRAME_HEIGHT}
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


PLAYER = Appearance(
    skin="#e4a672",
    hair_style="short",
    hair_colour="#3e2731",
    top_colour="#0099db",
    bottom_colour="#3a4466",
    shoe_colour="#ffffff",
    build="average",
    accessories=("backpack",),
)

SAMPLES: dict[str, Appearance] = {
    "sample_barista": Appearance(
        "#e8b98f", "bob", "#1c1b22", "#d9645a", "#2f3e5c", "#f2efe6", "slim", ("apron",)
    ),
    "sample_coder": Appearance(
        "#c28569", "buzz", "#262b44", "#5a6988", "#262b44", "#e43b44", "average",
        ("headphones", "glasses"),
    ),
    "sample_student": Appearance(
        "#ead4aa", "ponytail", "#733e39", "#f6757a", "#124e89", "#ffffff", "slim", ("backpack",)
    ),
    "sample_courier": Appearance(
        "#b86f50", "short", "#181425", "#feae34", "#3a4466", "#3a4466", "broad", ("cap",)
    ),
    "sample_artist": Appearance(
        "#e4a672", "curly", "#ff4fa8", "#68386c", "#3e8948", "#fee761", "average", ("scarf",)
    ),
    "sample_elder": Appearance(
        "#e8b796", "bald", "#c0cbdc", "#8b9bb4", "#3e2731", "#3e2731", "broad", ("glasses",)
    ),
    "sample_runner": Appearance(
        "#733e39", "long", "#181425", "#2ce8f5", "#262b44", "#63c74d", "slim", ("sunglasses",)
    ),
    "sample_skater": Appearance(
        "#c28569", "short", "#feae34", "#e43b44", "#5a6988", "#181425", "average", ("beanie",)
    ),
    "sample_teacher": Appearance(
        "#3e2731", "bun", "#181425", "#265c42", "#ead4aa", "#733e39", "average", ("glasses",)
    ),
    "sample_gardener": Appearance(
        "#e4a672", "curly", "#c0cbdc", "#3e8948", "#733e39", "#733e39", "broad", ("cap", "scarf")
    ),
}
