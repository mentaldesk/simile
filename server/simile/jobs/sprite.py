"""Draws one character's pixel-art sprite sheet with A1's generator, in a subprocess:
`python -m simile.jobs.sprite <work>`."""

import os
import sys
from pathlib import Path

from pydantic import field_validator
from pydantic_core import PydanticCustomError

from simile.jobs.report import progress
from simile.jobs.runner import CONTENT, Kind, url
from simile.schema import Appearance, Id, Model


class Sprite(Model):
    character: Id
    appearance: Appearance

    @field_validator("character")
    @classmethod
    def not_in_content(cls, character: str) -> str:
        if (CONTENT / "npcs" / f"{character}.json").exists() or (
            CONTENT / "art" / "characters" / f"{character}.png"
        ).exists():
            raise PydanticCustomError(
                "in_content", f"{character} has a sprite in content/, which jobs never change"
            )
        return character


def command(sprite: Sprite, work: Path) -> list[str]:
    return [sys.executable, "-m", "simile.jobs.sprite", str(work)]


def publish(sprite: Sprite, work: Path, out: Path) -> dict[str, str]:
    image, atlas = f"{sprite.character}.png", f"{sprite.character}.json"
    for name in (image, atlas):
        os.replace(work / name, out / name)
    return {"image": url("sprite", image), "atlas": url("sprite", atlas)}


SPRITE = Kind("sprite", Sprite, command, publish, files=r"[a-z][a-z0-9_]{0,63}\.(png|json)")


def main(work: Path) -> None:
    from simile.art.build import write_character

    sprite = Sprite.model_validate_json((work / "params.json").read_text())
    progress(0.0, "Drawing")
    write_character(work, sprite.character, sprite.appearance, seed=sprite.character)
    progress(1.0, "Drawn")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
