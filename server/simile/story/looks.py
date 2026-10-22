from simile.schema import Accessory, Appearance, HairStyle

HAIR = {
    "dark": "#1c1820",
    "brown": "#733e39",
    "grey": "#8b9bb4",
    "white": "#d4dbe6",
    "fair": "#e8c170",
    "red": "#b5502a",
    "blue": "#3a6ad8",
    "green": "#3e8948",
    "pink": "#e05a9a",
    "purple": "#7a4aa0",
}
CLOTHES = {
    "red": "#a22633",
    "dark red": "#6b1c24",
    "orange": "#f77622",
    "amber": "#feae34",
    "yellow": "#fee761",
    "green": "#3e8948",
    "dark green": "#265c42",
    "turquoise": "#2ce8f5",
    "teal": "#2a8a8a",
    "blue": "#124e89",
    "light blue": "#5a9bd8",
    "navy": "#1c2a4a",
    "purple": "#68386c",
    "pink": "#f6757a",
    "brown": "#733e39",
    "tan": "#c28569",
    "grey": "#8b9bb4",
    "black": "#181425",
    "white": "#ead4aa",
}
SEEN_IN_THE_DARK = {
    Accessory.SUNGLASSES: "sunglasses",
    Accessory.GLASSES: "glasses",
    Accessory.CAP: "a cap",
    Accessory.BEANIE: "a beanie",
    Accessory.SCARF: "a scarf",
    Accessory.HEADPHONES: "headphones",
    Accessory.BACKPACK: "a backpack",
}
COVERED = {Accessory.CAP, Accessory.BEANIE}


def nearest(colour: str, names: dict[str, str]) -> str:
    """The name in `names` whose colour is closest to `colour`."""

    def rgb(hex_colour: str) -> tuple[int, ...]:
        return tuple(int(hex_colour[i : i + 2], 16) for i in (1, 3, 5))

    here = rgb(colour)
    return min(
        names,
        key=lambda name: sum((a - b) ** 2 for a, b in zip(rgb(names[name]), here, strict=True)),
    )


def top(looks: Appearance) -> str:
    return nearest(looks.top_colour, CLOTHES)


def a(word: str) -> str:
    return f"an {word}" if word[:1] in "aeiou" else f"a {word}"


def figure(looks: Appearance) -> str:
    """How someone looks across a dark lane: "a grey-haired figure in a red top and sunglasses"."""
    worn = [item for item in looks.accessories if item in SEEN_IN_THE_DARK]
    if looks.hair_style is HairStyle.BALD:
        head = "a bald figure"
    elif any(item in COVERED for item in looks.accessories):
        head = "a figure"
    else:
        head = f"a {nearest(looks.hair_colour, HAIR)}-haired figure"
    dressed = f"{head} in {a(top(looks))} top"
    if not worn:
        return dressed
    joined = ", with" if worn[0] is Accessory.BACKPACK else " and"
    return f"{dressed}{joined} {SEEN_IN_THE_DARK[worn[0]]}"
