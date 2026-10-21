"""Paints a new or changed character's figure: `python -m simile.dolls.job <work>`."""

import os
import sys
import time
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path

from PIL import Image
from pydantic import field_validator
from pydantic_core import PydanticCustomError

from simile.dolls.flux import Painter
from simile.dolls.paint import NoPainter
from simile.jobs.report import progress
from simile.jobs.runner import CONTENT, Kind, url
from simile.schema import PLAYER_ID, Appearance, Id, Model

FILES = ("{}.json", "{}.webp")


class Doll(Model):
    character: Id
    appearance: Appearance

    @field_validator("character")
    @classmethod
    def not_in_content(cls, character: str) -> str:
        if character == PLAYER_ID:
            return character
        if (CONTENT / "npcs" / f"{character}.json").exists() or (
            CONTENT / "dolls" / f"{character}.json"
        ).exists():
            raise PydanticCustomError(
                "in_content", f"{character} has a doll in content/, which jobs never change"
            )
        return character


def command(doll: Doll, work: Path) -> list[str]:
    return [sys.executable, "-m", "simile.dolls.job", str(work)]


def publish(doll: Doll, work: Path, out: Path) -> dict[str, str]:
    manifest, painted = (name.format(doll.character) for name in FILES)
    for name in (painted, manifest):
        os.replace(work / name, out / name)
    return {"doll": url("doll", manifest), "painted": url("doll", painted)}


DOLL = Kind(
    "doll",
    Doll,
    command,
    publish,
    requires=("apple_silicon",),
    files=r"[a-z][a-z0-9_]{0,63}\.(json|webp)",
)


def persona_of(character: str) -> str:
    """Whether the library's character is a man or a woman, if it says."""
    from simile.dolls.words import persona
    from simile.library.store import Library, default_root

    try:
        return persona(gender=Library(default_root()).get(character).gender.value)
    except (LookupError, OSError, ValueError):
        return ""


def main(
    work: Path,
    painter: Callable[[], AbstractContextManager[Painter]] | None = None,
    cut: Callable[[Image.Image], Image.Image] | None = None,
) -> None:
    from simile.dolls.build import Cached, files, paint, write
    from simile.dolls.figure import FRAMES
    from simile.dolls.sprites import cut_out

    doll = Doll.model_validate_json((work / "params.json").read_text())
    if painter is None:
        from simile.dolls.flux import Flux

        painter = Flux
    progress(0.0, "Painting them standing")
    try:
        loading = painter()
    except NoPainter as error:
        sys.exit(str(error))
    done = [0]

    def painted(line: str) -> None:
        done[0] += 1
        progress(done[0] / len(FRAMES), f"Painted {done[0]} of {len(FRAMES)} poses")

    start = time.perf_counter()
    model = Cached(lambda: loading, None)
    said = "" if doll.character == PLAYER_ID else persona_of(doll.character)
    with model.stack:
        figure = paint(doll.character, doll.appearance, model, said, cut or cut_out, painted)
    appearance = doll.appearance.model_dump(mode="json")
    write(work, files(doll.character, figure, appearance=appearance))
    progress(1.0, f"Painted in {time.perf_counter() - start:.0f} s")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
