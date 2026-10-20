import os
import random
import shlex
import shutil
import threading
from collections.abc import Sequence
from datetime import datetime
from itertools import count as counting
from pathlib import Path
from typing import TYPE_CHECKING, Literal, Self

from pydantic import Field, model_validator
from starlette.applications import Starlette

from simile.casting import Bond, Cast, Pin, bind, cast, check_writable, village_houses, write_cast
from simile.schema import Character, CharacterSource, Id, Model

if TYPE_CHECKING:
    from simile.library import Library

REPO = Path(__file__).resolve().parents[3]
SERVER = REPO / "server"
DEFAULT_ROOT = SERVER / "worlds"
DOLLS = REPO / "content" / "dolls"
TODAY = "Today's village"


class NewWorld(Model):
    count: int = Field(ge=1)
    picks: list[Id] = Field(default=[], max_length=64)
    pins: list[Pin] = Field(default=[], max_length=64)
    seed: int | None = None

    @model_validator(mode="after")
    def _picked_once(self) -> Self:
        if len(set(self.picks)) != len(self.picks):
            raise ValueError("a character is picked twice")
        return self


class Resident(Model):
    id: Id
    name: str
    age: int
    occupation: str
    home: Id


class Missing(Model):
    id: Id
    name: str
    needs: list[Literal["voice", "sprite"]]


class Restart(Model):
    env: dict[str, str]
    command: str


class Current(Model):
    name: str
    default: bool = Field(description="Today's village: the residents in content/npcs/.")
    data: str | None = Field(description="Its data directory, or null for an in-memory one.")
    residents: list[Resident]


class Made(Model):
    name: str
    data: str
    seed: int
    residents: list[Resident]
    bonds: list[Bond]
    missing: list[Missing]
    restart: Restart


def default_root() -> Path:
    """`$SIMILE_WORLDS`, else `server/worlds/`."""
    return Path(os.environ.get("SIMILE_WORLDS") or DEFAULT_ROOT)


def shown(path: Path) -> str:
    """The path as `make dev`'s server, which runs in `server/`, would find it."""
    resolved = path.resolve()
    return str(resolved.relative_to(SERVER) if resolved.is_relative_to(SERVER) else resolved)


def current() -> Current:
    from simile.casting import data_directory, load_cast
    from simile.npc import load_npcs

    data, made = data_directory(), load_cast()
    return Current(
        name=data.name if made and data else TODAY,
        default=made is None,
        data=None if data is None else shown(data),
        residents=[
            Resident(id=n.id, name=n.name, age=n.age, occupation=n.occupation, home=n.home)
            for n in load_npcs()
        ],
    )


def houses() -> int:
    return len(village_houses())


class Worlds:
    """New worlds, each in a data directory of its own under `root`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.Lock()

    def draw(self, asked: NewWorld, library: "Library") -> list[Id]:
        return [r.character.id for r in _bound(asked, library, _seed(asked)).residents]

    def create(self, asked: NewWorld, library: "Library") -> Made:
        made = _bound(asked, library, _seed(asked))
        with self._lock:
            folder = self._new_folder()
            try:
                made = _with_clips(made, folder, library)
                write_cast(made, folder)
            except BaseException:
                shutil.rmtree(folder, ignore_errors=True)
                raise
        return _report(made, folder, library)

    def _new_folder(self) -> Path:
        stem = datetime.now().strftime("%Y-%m-%d-%H%M")
        names = (stem if n == 1 else f"{stem}-{n}" for n in counting(1))
        while True:
            folder = self.root / next(names)
            check_writable(folder)
            self.root.mkdir(parents=True, exist_ok=True)
            try:
                folder.mkdir()
                return folder
            except FileExistsError:
                pass


def worlds_of(app: Starlette) -> Worlds:
    if not hasattr(app.state, "worlds"):
        app.state.worlds = Worlds(default_root())
    return app.state.worlds


def _seed(asked: NewWorld) -> int:
    return random.SystemRandom().randrange(2**31) if asked.seed is None else asked.seed


def _bound(asked: NewWorld, library: "Library", seed: int) -> Cast:
    chosen = cast(library.characters(), asked.count, asked.picks, asked.pins, seed)
    return bind(chosen, asked.pins, seed)


def _with_clips(made: Cast, folder: Path, library: "Library") -> Cast:
    """Copies each player character's clip into the world, so it keeps its voice."""
    residents = []
    for resident in made.residents:
        character = resident.character
        if character.source is CharacterSource.PLAYER:
            clip, kept = library.clip(character), None
            if clip is not None and clip.is_file():
                copy = folder / "clips" / f"{character.id}.wav"
                copy.parent.mkdir(exist_ok=True)
                shutil.copyfile(clip, copy)
                kept = _from_repo(copy)
            voice = character.voice.model_copy(update={"reference_clip": kept})
            character = character.model_copy(update={"voice": voice})
        residents.append(resident.model_copy(update={"character": character}))
    return made.model_copy(update={"residents": residents})


def _from_repo(path: Path) -> str:
    resolved = path.resolve()
    return str(resolved.relative_to(REPO) if resolved.is_relative_to(REPO) else resolved)


def _report(made: Cast, folder: Path, library: "Library") -> Made:
    env = {"SIMILE_DB": shown(folder / "simile.db")}
    if library.root != (folder / "library").resolve():
        env["SIMILE_LIBRARY"] = shown(library.root)
    return Made(
        name=folder.name,
        data=shown(folder),
        seed=made.seed,
        residents=[_resident(made, r.character, r.home) for r in made.residents],
        bonds=made.bonds,
        missing=_missing([r.character for r in made.residents]),
        restart=Restart(
            env=env,
            command=" ".join(f"{k}={shlex.quote(v)}" for k, v in env.items()) + " make dev",
        ),
    )


def _resident(made: Cast, character: Character, home: Id) -> Resident:
    return Resident(
        id=character.id,
        name=character.name,
        age=made.age(character),
        occupation=character.occupation,
        home=home,
    )


def _missing(characters: Sequence[Character]) -> list[Missing]:
    found = []
    for character in characters:
        needs: list[Literal["voice", "sprite"]] = []
        if character.voice.reference_clip is None:
            needs.append("voice")
        if not (DOLLS / f"{character.id}.json").is_file():
            needs.append("sprite")
        if needs:
            found.append(Missing(id=character.id, name=character.name, needs=needs))
    return found
