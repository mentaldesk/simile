"""The greetings job, which records a player character's greetings once its voice is set."""

import hashlib
import json
import logging
import os
import shutil
import sys
from collections.abc import Mapping, Sequence
from datetime import date
from pathlib import Path
from typing import Any

from starlette.concurrency import run_in_threadpool

from simile.jobs import Busy, Jobs, Kind
from simile.library import Library, Refused
from simile.schema import Id, Model
from simile.voicelib.config import DEFAULT_CONFIG, VoicelibConfig
from simile.voicelib.kinds import MLX_PYTHON
from simile.voicing import speak
from simile.voicing.greetings import (
    DELIVERIES,
    GREETINGS,
    files,
    lines_for,
    load_chosen,
    players,
    remove,
    tones,
)

logger = logging.getLogger(__name__)

GREET = "voice_greetings"
NEEDS = ("apple_silicon", "voice_lab_mlx")
ELEVENLABS_NEEDS = ("apple_silicon",)
SCRIPT = Path(speak.__file__)
ELEVENLABS = "simile.voicing.eleven"


class Greet(Model):
    character: Id
    library: Id | None = None


def command(params: Greet, work: Path) -> Sequence[str]:
    # -I keeps the script's own folder, simile/voicing/, off sys.path.
    return [str(MLX_PYTHON), "-I", str(SCRIPT), str(work)]


def elevenlabs_command(params: Greet, work: Path) -> Sequence[str]:
    return [sys.executable, "-I", "-m", ELEVENLABS, str(work)]


def today() -> date:
    return date.today()


class Allowance:
    """The ElevenLabs characters the greetings jobs may still send today, kept in `path`."""

    def __init__(self, path: Path, daily: int) -> None:
        self.path, self.daily = path, daily

    def spent(self) -> int:
        try:
            kept = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return 0
        return int(kept["characters"]) if kept.get("day") == today().isoformat() else 0

    def take(self, characters: int) -> bool:
        """Counts them against today's allowance, unless they'd go over it."""
        spent = self.spent()
        if spent + characters > self.daily:
            return False
        self.path.parent.mkdir(parents=True, exist_ok=True)
        kept = {"day": today().isoformat(), "characters": spent + characters}
        written = self.path.with_name(f".{self.path.name}.{os.getpid()}")
        written.write_text(json.dumps(kept), encoding="utf-8")
        os.replace(written, self.path)
        return True


def said_in(root: Path, clip: Path, asked: Mapping[str, Any]) -> Path:
    """Where ElevenLabs' greetings for this voice and these lines are kept, to say them once."""
    voice = {k: v for k, v in asked.items() if k not in ("clip", "clip_changed")}
    voice["clip"] = hashlib.sha256(clip.read_bytes()).hexdigest()
    digest = hashlib.sha256(json.dumps(voice, sort_keys=True).encode()).hexdigest()
    return root / GREET / "said" / digest[:32]


def kind(library: Library, config: VoicelibConfig = DEFAULT_CONFIG) -> Kind[Greet]:
    """Says `lines_for` the character with ElevenLabs if there's a key, or in its own voice."""
    from simile.voicing import eleven

    with_elevenlabs = eleven.configured()

    def prepare(params: Greet, work: Path) -> Sequence[str]:
        character = library.get(params.character)
        clip = library.clip(character)
        if library.is_premade(character.id) or clip is None or not clip.is_file():
            raise Refused(f"{character.name} has no voice of their own yet")
        asked: dict[str, Any] = {
            "voice": character.id,
            "clip": str(clip),
            "clip_changed": clip.stat().st_mtime_ns,
            "transcript": character.voice.reference_line,
            "lines": lines_for(character),
        }
        run = command
        if with_elevenlabs:
            resident = load_chosen().get(params.library or "")
            asked |= {
                "delivery": DELIVERIES[tones(character)[0]],
                "elevenlabs": resident and {"voice_id": resident.voice, "name": resident.name},
                "gender": eleven.GENDERS.get(character.gender),
                "age": eleven.age_band(character.updated.year - character.birth_year),
                "places": eleven.places(character.voice.description, character.origin),
            }
            root = work.parents[1]
            said = said_in(root, clip, asked)
            asked["said"] = str(said)
            cost = sum(len(f"{asked['delivery']} {line}".strip()) for line in asked["lines"])
            allowance = Allowance(
                root / GREET / "allowance.json", config.elevenlabs_characters_a_day
            )
            if files(said, character.id) or allowance.take(cost):
                run = elevenlabs_command
            elif not MLX_PYTHON.exists():
                raise Refused(
                    f"Today's {allowance.daily} ElevenLabs characters are spent, and this machine "
                    "can't say greetings with V1's model"
                )
            else:
                logger.warning(
                    f"Today's {allowance.daily} ElevenLabs characters are spent, so V1's model "
                    f"says {character.name}'s greetings"
                )
        (work / "greetings.json").write_text(json.dumps(asked), encoding="utf-8")
        return run(params, work)

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
            "voice": spoken.get("voice"),
        }

    return Kind(GREET, Greet, prepare, publish, ELEVENLABS_NEEDS if with_elevenlabs else NEEDS)


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
            jobs.submit(GREET, {"character": id, "library": voice})
        except Busy as error:
            logger.warning(f"No new greetings for {id}: {error}")
    elif voice is not None:
        await run_in_threadpool(borrow, library, id, voice)
