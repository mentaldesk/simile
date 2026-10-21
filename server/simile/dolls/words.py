"""A resident in words for the painter: who they are, their skin, hair, clothes and accessories,
each colour named as precisely as FLUX follows it. It follows names, not hex codes."""

import re

from simile.dolls.paint import STYLES, WEARS, an
from simile.schema import Appearance

COLOURS = {
    "ink": "near-black",
    "night": "very dark navy blue",
    "slate": "dark slate blue",
    "steel": "muted blue-grey",
    "concrete": "light blue-grey",
    "pavement": "pale silver-grey",
    "white": "pure white",
    "ice": "pale icy blue",
    "cream": "cream",
    "peach": "light peach",
    "sand": "sandy tan",
    "tan": "warm tan",
    "brown": "terracotta brown",
    "umber": "dark reddish brown",
    "espresso": "very dark brown",
    "maroon": "deep crimson red",
    "red": "bright red",
    "orange": "bright orange",
    "amber": "golden amber yellow",
    "yellow": "lemon yellow",
    "lime": "lime green",
    "green": "medium grass green",
    "forest": "dark forest green",
    "deep": "very dark teal",
    "navy": "deep cobalt blue",
    "blue": "bright sky blue",
    "cyan": "bright cyan",
    "plum": "dark plum purple",
    "magenta": "raspberry magenta",
    "pink": "coral pink",
    "neon": "hot pink",
    "violet": "violet",
}
"""Each palette colour by a name that says its hue and how light and strong it is."""
SKIN = {
    "cream": "very pale cream",
    "peach": "light peach",
    "sand": "golden tan",
    "tan": "light brown",
    "brown": "brown",
    "umber": "deep dark brown",
}
HAIR = {
    "ink": "black",
    "night": "black",
    "espresso": "very dark brown",
    "umber": "dark auburn brown",
    "brown": "chestnut brown",
    "concrete": "blue-grey",
    "steel": "dark blue-grey",
    "pavement": "silver",
    "white": "white",
    "cream": "pale blonde",
    "sand": "sandy blonde",
    "yellow": "golden blonde",
    "amber": "golden",
}
BUILD = {"slim": "slim", "average": "medium build", "broad": "broad and stocky"}
GENDERS = {
    "woman": r"\b(woman|lady|auntie|girl|grandmother|she)\b",
    "man": r"\b(man|gentleman|uncle|boy|grandfather|he)\b",
}


def colour(hex_colour: str, names: dict[str, str] = COLOURS) -> str:
    from simile.characters.palette import PALETTE, hex_to_rgb, nearest

    name = nearest(hex_to_rgb(hex_colour), tuple(PALETTE))
    return names.get(name, COLOURS.get(name, name))


def gender_in(text: str) -> str | None:
    """`woman` or `man` if `text`, such as a voice's description, says which."""
    found = [(m.start(), g) for g, word in GENDERS.items() if (m := re.search(word, text, re.I))]
    return min(found)[1] if found else None


def persona(age: int | None = None, gender: str | None = None) -> str:
    """`A woman of 27.`, as far as it's known. The `Appearance` has neither, and FLUX guesses
    from hair and clothes."""
    who = gender if gender in ("woman", "man") else "person"
    if age is None:
        return "" if who == "person" else f"A {who}."
    return f"A {who} of {age}."


def described(appearance: Appearance, who: str | None) -> str:
    """Their skin, hair, accessories, clothes and build."""
    from simile.characters.palette import PALETTE, accent, apron

    style = appearance.hair_style.value
    hair = (
        "a bald head"
        if style == "bald"
        else STYLES[style].format(colour(appearance.hair_colour, HAIR))
    )
    worn = colour(PALETTE[accent(appearance, seed=who)])
    colours = {
        "accent": worn,
        "a_accent": an(worn),
        "a_apron": an(colour(PALETTE[apron(appearance)])),
    }
    wears = [WEARS[a.value].format(**colours) for a in appearance.accessories]
    also = f", and wears {' and '.join(wears)}" if wears else ""
    top, bottom = colour(appearance.top_colour), colour(appearance.bottom_colour)
    return (
        f"The person has {colour(appearance.skin, SKIN)} skin and {hair}{also}. They are "
        f"{BUILD[appearance.build.value]}, in {an(top)} t-shirt, {bottom} trousers and "
        f"{colour(appearance.shoe_colour)} sneakers."
    )
