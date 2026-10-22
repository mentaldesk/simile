"""The greetings job, which records a player character's greetings once its voice is set."""

import json
import logging
import os
import shutil
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from simile.jobs import Busy, Jobs, Kind
from simile.library import Library, Refused
from simile.schema import Id, Model
from simile.voicelib.kinds import MLX_PYTHON
from simile.voicing import speak
from simile.voicing.greetings import GREETINGS, files, lines_for, players, remove

logger = logging.getLogger(__name__)

GREET = "voice_greetings"
NEEDS = ("apple_silicon", "voice_lab_mlx")
SCRIPT = Path(speak.__file__)


class Greet(Model):
    character: Id


def command(params: Greet, work: Path) -> Sequence[str]:
    # -I keeps the script's own folder, simile/voicing/, off sys.path.
    return [str(MLX_PYTHON), "-I", str(SCRIPT), str(work)]


def kind(library: Library) -> Kind[Greet]:
    """Says `lines_for` the character in its voice, into `players(library)`."""

    def prepare(params: Greet, work: Path) -> Sequence[str]:
        character = library.get(params.character)
        clip = library.clip(character)
        if library.is_premade(character.id) or clip is None or not clip.is_file():
            raise Refused(f"{character.name} has no voice of their own yet")
        asked = {
            "voice": character.id,
            "clip": str(clip),
            "clip_changed": clip.stat().st_mtime_ns,
            "transcript": character.voice.reference_line,
            "lines": lines_for(character),
        }
        (work / "greetings.json").write_text(json.dumps(asked), encoding="utf-8")
        return command(params, work)

    def publish(params: Greet, work: Path, out: Path) -> dict[str, Any]:
        asked = json.loads((work / "greetings.json").read_text(encoding="utf-8"))
        spoken = json.loads((work / "spoken.json").read_text(encoding="utf-8"))
        clip = Path(asked["clip"])
        stale = not clip.is_file() or clip.stat().st_mtime_ns != asked["clip_changed"]
        folder = players(library)
        if not stale:
            folder.mkdir(parents=True, exist_ok=True)
            remove(folder, params.character)
            for path in files(work, params.character):
                os.replace(path, folder / path.name)
        made = [] if stale else files(folder, params.character)
        return {
            "greetings": [f"/api/greetings/{params.character}/{path.name}" for path in made],
            "lines": asked["lines"],
            "seconds": spoken["seconds"],
            "stale": stale,
        }

    return Kind(GREET, Greet, prepare, publish, NEEDS)


def borrow(library: Library, id: str, voice: str) -> None:
    """Copies a library voice's greetings, said by the resident it belongs to."""
    folder = players(library)
    folder.mkdir(parents=True, exist_ok=True)
    for n, path in enumerate(files(GREETINGS, voice), 1):
        shutil.copyfile(path, folder / f"{id}_{n}{path.suffix}")


async def regreet(jobs: Jobs, library: Library, id: str, voice: str | None = None) -> None:
    """Drops a character's old greetings and makes new ones, or borrows a library voice's."""
    await run_in_threadpool(remove, players(library), id)
    if jobs.capabilities()["kinds"].get(GREET, {}).get("available", False):
        try:
            jobs.submit(GREET, {"character": id})
        except Busy as error:
            logger.warning(f"No new greetings for {id}: {error}")
    elif voice is not None:
        await run_in_threadpool(borrow, library, id, voice)
