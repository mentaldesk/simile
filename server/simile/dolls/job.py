"""Paints a new or changed character's doll: `python -m simile.dolls.job <work>`. Shaped like
`jobs/sprite.py`, which part 9 replaces with it; nothing registers it yet."""

import importlib.util
import os
import sys
import tempfile
from collections.abc import Callable
from contextlib import AbstractContextManager
from pathlib import Path
from typing import Any

from pydantic import field_validator
from pydantic_core import PydanticCustomError

from simile.dolls.paint import SheetPainter
from simile.jobs.report import progress
from simile.jobs.runner import CONTENT, Kind, url
from simile.schema import PLAYER_ID, Appearance, Id, Model

FILES = ("{}.json", "{}-flat.webp", "{}-painted.webp")


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
    manifest, flat, painted = (name.format(doll.character) for name in FILES)
    for name in (flat, painted, manifest):
        os.replace(work / name, out / name)
    return {
        "doll": url("doll", manifest),
        "flat": url("doll", flat),
        "painted": url("doll", painted),
    }


DOLL = Kind(
    "doll",
    Doll,
    command,
    publish,
    requires=("apple_silicon",),
    files=r"[a-z][a-z0-9_]{0,63}(\.json|-flat\.webp|-painted\.webp)",
)


class Reporting:
    """Reports each sheet as the job's progress."""

    def __init__(self, model: SheetPainter, sheets: int) -> None:
        self.model, self.sheets, self.done = model, sheets, 0

    def paint(self, *args: Any) -> Any:
        progress(0.05 + 0.9 * self.done / self.sheets, f"Painting {self.done + 1} of {self.sheets}")
        painted = self.model.paint(*args)
        self.done += 1
        return painted


def main(work: Path, painter: Callable[[], AbstractContextManager[SheetPainter]] | None = None):
    from simile.dolls.build import files, paint, write
    from simile.dolls.sheet import LAYOUTS

    doll = Doll.model_validate_json((work / "params.json").read_text())
    if painter is None:
        if importlib.util.find_spec("mflux") is None:
            sys.exit("Doll jobs need the images extra: `uv sync --extra images`.")
        from simile.dolls.flux import FluxEdit

        painter = FluxEdit
    progress(0.0, "Cutting out")
    with painter() as model, tempfile.TemporaryDirectory() as scratch:
        reporting = Reporting(model, len(LAYOUTS))
        painted = paint(doll.character, doll.appearance, reporting, Path(scratch), cache=None)
    appearance = doll.appearance.model_dump(mode="json")
    write(work, files(doll.character, painted.doll, appearance=appearance))
    progress(1.0, "Painted")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
