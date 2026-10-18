from collections.abc import Callable, Sequence
from datetime import datetime

from simile.behaviour import Options
from simile.behaviour.intentions import deed, when
from simile.schema import Id, Intention, Medium

CANVAS = "paint a canvas for the gallery"


def can_do(options: Options, name: str | None = None) -> str:
    """What a resident could plan to do in the village, told to them or, with `name`, about
    them, so they only promise what they can do."""
    places = [place for id, place in options.places.items() if id != options.home]
    things = [
        "go home",
        f"go to {listed(places, 'or')}",
        "read the news at a terminal",
        "look someone up for a chat",
    ]
    note = ""
    if (craft := making(options)) is not None:
        things.append(craft)
    elif options.medium is Medium.MURAL:
        note = " No wall is ready for a mural now."
    if name is None:
        return (
            f"What you could plan to do in the village: {choices(things)}.{note} Only promise "
            "what's on this list, and nothing further off than tomorrow."
        )
    return (
        f"What {name} could plan to do in the village: {choices(things)}.{note} {name} only "
        "promises what's on this list, and nothing further off than tomorrow."
    )


def making(options: Options) -> str | None:
    """Where they could make something now, or None if nowhere."""
    if options.medium is None or not options.making:
        return None
    if options.medium is Medium.MURAL:
        walls = [name for id, name in options.making.items() if id not in options.places]
        if walls:
            return f"paint a mural on {walls[0]}"
        return f"{CANVAS} at home, since no wall is ready for a mural"
    where = listed([_place(id, name, options) for id, name in options.making.items()], "or")
    return f"write at {where}" if options.medium is Medium.WRITING else f"{CANVAS} at {where}"


def already(
    intentions: Sequence[Intention],
    now: datetime,
    name_of: Callable[[Id], str],
    name: str | None = None,
) -> str:
    """What a resident has already said they'd do, so they keep to it."""
    lines = []
    for intention in intentions:
        told = ", ".join(name_of(id) for id in intention.promised_to)
        to = f"told {told}, " if told else ""
        lines.append(f"- {deed(intention)} ({to}{when(intention.due, now)})")
    if name is None:
        return "You've already said you'd do these, so keep to them:\n" + "\n".join(lines)
    return f"{name} has already said they'd do these, and keeps to them:\n" + "\n".join(lines)


def choices(things: Sequence[str]) -> str:
    return "; ".join([*things[:-1], f"or {things[-1]}"])


def listed(items: Sequence[str], word: str = "and") -> str:
    if len(items) <= 1:
        return "".join(items)
    return f"{', '.join(items[:-1])} {word} {items[-1]}"


def _place(id: Id, name: str, options: Options) -> str:
    return "home" if id == options.home else name
