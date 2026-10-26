"""What each icon is painted from: words, in the style of the tunnels' cartoon reference."""

from dataclasses import dataclass

from simile.creatures.catalogue import Box
from simile.papercraft.painter import cartoon, grimy

WHOLE: Box = (0.0, 0.0, 1.0, 1.0)
ABOVE_THE_FEET: Box = (0.0, 0.0, 1.0, 0.84)
LOOKS = {"cartoon": cartoon, "grimy": grimy}
LEAD = "Make a new picture in exactly the {look} style of the reference picture: a 2D game icon: "
ALONE = (
    " Shown whole and alone in the middle of the picture, filling most of it, on a plain flat "
    "light grey background with nothing else in the picture, and no shadow on the background."
)


@dataclass(frozen=True)
class Icon:
    id: str
    words: str
    pieces: int = 1
    """How many separate pieces it's in, such as 2 for a pair of feet."""
    look: str = "cartoon"
    """`LOOKS`: #329's cartoon, or its grimy version."""
    tries: int = 3
    reroll: int = 0
    """A reroll number, for one that came out wrong by eye."""
    keep: Box = WHOLE
    """The share of it kept, as shares of its box."""

    def prompt(self) -> str:
        return LOOKS[self.look](LEAD.format(look=self.look) + self.words + ALONE)


def scar(shape: str) -> str:
    return (
        f"{shape} of pale pink skin where a body part was cut out, sewn shut along a red scar "
        "with thick black criss-cross surgical stitches, a bit of dried blood."
    )


ORGANS = (
    Icon(
        "eye",
        "a single human eyeball seen from the front: a white ball with a brown iris and a black "
        "pupil, a few thin red veins, and a short pink nerve stalk behind it.",
    ),
    Icon(
        "vertebra",
        "a short upright stretch of human spine: three off-white bony vertebrae stacked one on "
        "another with pale pink discs between them, seen from the front.",
    ),
    Icon(
        "stomach",
        "a human stomach organ like an anatomy chart's: a plump pink J-shaped bag with a short "
        "tube at its top and its bottom.",
    ),
    Icon(
        "kidney",
        "a single human kidney: a plump dark reddish-brown bean shape with a short pale tube and "
        "two blood vessels coming out of its inner curve.",
    ),
    Icon(
        "legs",
        "a pair of bare human legs side by side, standing straight, light brown skin, knobbly "
        "knees, from the thighs down to the ankles and cut off cleanly there: no feet at all, "
        "each leg ending in a flat round stump at the ankle.",
        pieces=2,
        keep=ABOVE_THE_FEET,
    ),
    Icon(
        "feet",
        "a pair of bare human feet side by side seen from above, toes pointing up, light brown "
        "skin.",
        pieces=2,
    ),
)
SOLD = (
    Icon("eye_sold", scar("a small round patch")),
    Icon("vertebra_sold", scar("a tall narrow upright strip")),
    Icon("stomach_sold", scar("a plump J-shaped patch")),
    Icon("kidney_sold", scar("a bean-shaped patch")),
    Icon("legs_sold", scar("two tall narrow upright strips side by side"), pieces=2),
    Icon("feet_sold", scar("two small oval patches side by side"), pieces=2),
)
"""Where an organ was, sold: `<organ>_sold`."""
BIONICS = (
    Icon(
        "power_cell",
        "a chunky bionic power cell: a rounded steel-grey cylinder battery lying on its side, "
        "copper terminals at its ends, a glowing green charge window along it and a few coloured "
        "wires.",
    ),
    Icon(
        "datajack",
        "a short upright stretch of bionic chrome spine: three stacked steel vertebrae, the "
        "middle one with a chunky round chrome datajack socket set in it, a bright green light in "
        "the socket's middle.",
    ),
    Icon(
        "infrared_eye",
        "a bionic eyeball seen from the front: a steel-grey metal ball with a bright glowing red "
        "lens in a thin chrome rim, a few thin wires trailing behind it.",
    ),
    Icon(
        "hydraulic_legs",
        "a pair of bionic hydraulic legs side by side, from the thighs down to the ankles and "
        "no further, no feet at all: bare steel-grey machinery with a shiny chrome hydraulic "
        "piston down each shin and a round metal knee joint.",
        pieces=2,
        keep=ABOVE_THE_FEET,
    ),
    Icon(
        "bionic_legs",
        "a pair of sleek bionic legs side by side, from the thighs down to the ankles and no "
        "further, no feet at all: smooth streamlined robot legs of rounded steel-grey armour "
        "plates, like a racing robot's, with a black rubber joint at each knee.",
        pieces=2,
        keep=ABOVE_THE_FEET,
    ),
    Icon(
        "spring_feet",
        "a pair of bionic spring feet side by side: flat steel-grey metal foot plates shaped like "
        "shoes, each with a chunky bright yellow coil spring at the heel.",
        pieces=2,
    ),
)
"""Each bionic's picture, by its line: every grade of a line shares it, and stage 1's legs show
as the hydraulic legs."""

ICONS: dict[str, Icon] = {icon.id: icon for icon in (*ORGANS, *SOLD, *BIONICS)}
