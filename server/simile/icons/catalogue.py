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

ITEMS = (
    Icon(
        "lamp",
        "a battered handheld electric lantern: a chunky dark green metal body with a curved carry "
        "handle on top and a round glass lens on its front glowing warm yellow.",
    ),
    Icon(
        "ration_pack",
        "a sealed khaki foil ration pack: a flat rectangular food pouch with crimped edges, a "
        "printed white label and a torn-off notch at one corner.",
    ),
    Icon(
        "copper_wire",
        "a coil of bare shiny copper wire wound round and round in a loose bundle, one loose end "
        "sticking out.",
    ),
    Icon(
        "scrap_steel",
        "a small stack of rusty scrap steel: a few bent flat steel plates and a short girder, "
        "dark grey with orange rust patches and bolt holes.",
    ),
    Icon(
        "circuit_board",
        "a single green electronic circuit board seen from the front: gold tracks, little black "
        "chips and a few coloured components, one corner snapped off.",
    ),
    Icon(
        "brass_valve",
        "a chunky old brass water valve: a round brass body with a pipe stub at each side and a "
        "red iron wheel handle on top.",
    ),
    Icon(
        "signal_relay",
        "an old railway signal relay: a small grey metal box with a clear glass window on its "
        "front showing copper coils inside, and screw terminals along its top.",
    ),
    Icon(
        "servo_motor",
        "a chunky electric servo motor: a dark grey metal cylinder motor with a small gearbox and "
        "a white output shaft on its front, and three coloured wires coming out of its back.",
    ),
    Icon(
        "lead_pipe",
        "a short dull grey lead pipe, bent once in the middle, with dented ends, lying on its "
        "side.",
    ),
    Icon(
        "copper_coil",
        "a copper electromagnet coil: tightly wound shiny copper wire on a black plastic bobbin, "
        "two wire ends sticking out.",
    ),
    Icon(
        "brass_fitting",
        "a single brass plumbing fitting: a shiny brass T-shaped pipe joint with screw threads "
        "and a hexagonal nut at each of its three ends.",
    ),
    Icon(
        "pump_impeller",
        "a pump impeller seen from the front: a round steel-grey wheel of curved blades around a "
        "hub with a hole in its middle, a bit of green slime on it.",
    ),
    Icon(
        "float_valve",
        "a toilet cistern float valve: a round orange plastic float ball on the end of a long "
        "thin brass arm, the other end of the arm in a small brass valve.",
    ),
    Icon(
        "filter_mesh",
        "a square of grimy steel filter mesh: a fine wire grid in a thin metal frame, bent at one "
        "corner, with brown muck caught in it.",
    ),
    Icon(
        "old_battery",
        "a big old car battery: a black plastic box with a red and a black terminal on its top, "
        "a faded label and a white crust on one terminal.",
    ),
    Icon(
        "pressure_gauge",
        "an old round pressure gauge: a brass dial with a white face, black numbers and a red "
        "needle behind cracked glass, and a short threaded brass stem below it.",
    ),
    Icon(
        "apex_board",
        "a sleek high-tech control board: a dark blue circuit board with fine silver tracks, a "
        "big square chip in its middle and a small glowing white logo light.",
    ),
    Icon(
        "lithium_cell",
        "a single cylindrical lithium battery cell standing upright: a shiny blue metal tube "
        "with a silver cap on top and a thin white label band.",
    ),
    Icon(
        "charge_controller",
        "a small electronic charge controller: a black plastic box with a tiny screen showing "
        "green numbers, a few little lights and screw terminals along its bottom edge.",
    ),
    Icon(
        "usb_c_connector",
        "a single USB-C connector plug: a small silver oval metal plug on a short black rubber "
        "body, with a stub of black cable coming out of its back.",
    ),
    Icon(
        "infrared_lens",
        "one single round lens seen straight from the front: a thick black metal ring around a "
        "deep red glowing glass disc, like one loose camera lens, nothing beside it.",
    ),
    Icon(
        "apex_actuator",
        "a chunky high-tech robot joint actuator standing upright: a short fat smooth white "
        "cylinder with chrome caps at both ends, a glowing blue ring round its middle and a short "
        "shiny piston rod sticking out of its top.",
    ),
)
UNKNOWN = Icon(
    "unknown_item",
    "a small battered brown cardboard box tied up with string, a big black question mark "
    "scrawled on its side.",
)
"""The picture of an item with none of its own yet."""

ICONS: dict[str, Icon] = {icon.id: icon for icon in (*ORGANS, *SOLD, *BIONICS, *ITEMS, UNKNOWN)}
