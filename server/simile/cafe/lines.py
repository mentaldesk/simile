import json
import random
from pathlib import Path

from simile.cafe.menu import CAFE_DIR


class Lines:
    """The stock lines of a cheap order, from `content/cafe/lines.json`."""

    def __init__(self, path: Path = CAFE_DIR / "lines.json") -> None:
        self.options: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8"))

    def pick(self, kind: str, rng: random.Random, **names: str) -> str:
        """One of the `kind` lines, with `{customer}`, `{barista}` and `{drink}` filled in,
        `{a_drink}` with its article, and either capitalised as `{Drink}` or `{A_drink}`."""
        if drink := names.get("drink"):
            names["a_drink"] = f"{'an' if drink[0].lower() in 'aeiou' else 'a'} {drink}"
            names["Drink"], names["A_drink"] = _capital(drink), _capital(names["a_drink"])
        return rng.choice(self.options[kind]).format_map(names)


def _capital(text: str) -> str:
    return text[0].upper() + text[1:]
