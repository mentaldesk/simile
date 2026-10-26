import os
import random
import re
import shlex
import shutil
import threading
from collections.abc import Sequence
from datetime import datetime
from itertools import count as counting
from pathlib import Path
from typing import TYPE_CHECKING, Annotated, Literal, Self

from pydantic import Field, StringConstraints, model_validator
from starlette.applications import Starlette

from simile.casting import Bond, Cast, Pin, bind, cast, check_writable, village_houses, write_cast
from simile.memory.store import DEFAULT_PATH
from simile.schema import Character, CharacterSource, Id, Model
from simile.worlds.index import Entry, Index, Played
from simile.worlds.saves import progress

if TYPE_CHECKING:
    from simile.library import Library

REPO = Path(__file__).resolve().parents[3]
SERVER = REPO / "server"
DEFAULT_ROOT = SERVER / "worlds"
DOLLS = REPO / "content" / "dolls"
TODAY = "Today's village"
TODAY_ID = "today"
DATABASE = "simile.db"
FOLDER = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")
MADE_FORMAT = "%Y-%m-%d-%H%M"
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class NotFound(Exception):
    pass


class Refused(Exception):
    pass


class NewWorld(Model):
    count: int = Field(ge=1)
    picks: list[Id] = Field(default=[], max_length=64)
    pins: list[Pin] = Field(default=[], max_length=64)
    seed: int | None = None
    name: Name | None = Field(default=None, description="Its name, else when it was made.")
    open: bool = Field(default=False, description="Open it once it's made.")

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
    id: str | None = Field(description="Its id in the list of worlds, or null if it isn't one.")
    name: str
    default: bool = Field(description="Today's village: the residents in content/npcs/.")
    data: str | None = Field(description="Its data directory, or null for an in-memory one.")
    residents: list[Resident]


class Made(Model):
    id: str
    name: str
    data: str
    seed: int
    residents: list[Resident]
    bonds: list[Bond]
    missing: list[Missing]
    restart: Restart
    opening: bool = Field(default=False, description="Whether the server is switching to it.")


class World(Model):
    id: str
    name: str
    default: bool = Field(description="Today's village, which can't be deleted.")
    running: bool
    made: datetime | None
    played: datetime | None = Field(description="When it was last played, if ever.")
    day: int | None = Field(description="The in-game day it's saved on, from 1, if it's saved.")
    time: datetime | None = Field(description="The sim time it's saved at, if it's saved.")
    player: str
    residents: int


def default_root() -> Path:
    """`$SIMILE_WORLDS`, else `server/worlds/`."""
    return Path(os.environ.get("SIMILE_WORLDS") or DEFAULT_ROOT)


def shown(path: Path) -> str:
    """The path as `make dev`'s server, which runs in `server/`, would find it."""
    resolved = path.resolve()
    return str(resolved.relative_to(SERVER) if resolved.is_relative_to(SERVER) else resolved)


def current(root: Path | None = None) -> Current:
    from simile.casting import data_directory, load_cast
    from simile.npc import load_npcs

    root = root or default_root()
    data, made = data_directory(), load_cast()
    id = running(root)
    named = Index(root).read().entry(id).name if id else None
    return Current(
        id=id,
        name=named or (data.name if made and data else TODAY),
        default=made is None,
        data=None if data is None else shown(data),
        residents=[
            Resident(id=n.id, name=n.name, age=n.age, occupation=n.occupation, home=n.home)
            for n in load_npcs()
        ],
    )


def running(root: Path, database: Path | None = None) -> str | None:
    """The id of the world the server runs, or the one whose save is `database`, or None if it
    isn't one of the worlds."""
    from simile.casting import data_directory

    data = data_directory() if database is None else _folder(database)
    if data is None:
        return None
    if _same(data, DEFAULT_PATH.parent):
        return TODAY_ID
    if _same(data.parent, root) and _is_world(data):
        return data.name
    return None


def houses() -> int:
    return len(village_houses())


class Worlds:
    """New worlds, each in a data directory of its own under `root`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self._lock = threading.Lock()

    def draw(self, asked: NewWorld, library: "Library") -> list[Id]:
        return [r.character.id for r in _bound(asked, library, _seed(asked)).residents]

    @property
    def index(self) -> Index:
        return Index(self.root)

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
        entry = Entry(name=asked.name, made=datetime.now().astimezone())

        def record(played: Played) -> None:
            played.worlds[folder.name] = entry

        self.index.change(record)
        return _report(made, folder, library, asked.name)

    def ids(self) -> list[str]:
        """Today's village, then the new worlds, newest first."""
        found = (p.name for p in self.root.iterdir()) if self.root.is_dir() else iter(())
        return [TODAY_ID, *sorted((n for n in found if self._world(n)), reverse=True)]

    def database(self, id: str) -> Path:
        self.check(id)
        return DEFAULT_PATH if id == TODAY_ID else self.root / id / DATABASE

    def check(self, id: str) -> None:
        if id != TODAY_ID and not self._world(id):
            raise NotFound(f"There's no world {id!r}")

    def worlds(self) -> list[World]:
        from simile.social import DEFAULT_BIONICS

        played, now = self.index.read(), running(self.root)
        return [self._listed(id, played, now, DEFAULT_BIONICS.player_name) for id in self.ids()]

    def world(self, id: str) -> World:
        from simile.social import DEFAULT_BIONICS

        self.check(id)
        return self._listed(id, self.index.read(), running(self.root), DEFAULT_BIONICS.player_name)

    def rename(self, id: str, name: str) -> World:
        self.check(id)

        def change(played: Played) -> None:
            played.worlds[id] = played.entry(id).model_copy(update={"name": name})

        self.index.change(change)
        return self.world(id)

    def delete(self, id: str) -> None:
        if id == TODAY_ID:
            raise Refused(f"{TODAY} can't be deleted")
        self.check(id)
        if running(self.root) == id:
            raise Refused("The world the server is running can't be deleted. Open another first")
        with self._lock:
            shutil.rmtree(self.root / id)

        def change(played: Played) -> None:
            played.worlds.pop(id, None)
            if played.last == id:
                played.last = None

        self.index.change(change)

    def _world(self, id: str) -> bool:
        return FOLDER.fullmatch(id) is not None and _is_world(self.root / id)

    def _listed(self, id: str, played: Played, now: str | None, player: str) -> World:
        from simile.casting import load_cast
        from simile.npc import NPCS_DIR, load_npcs

        entry, saved = played.entry(id), progress(self.database(id))
        if id == TODAY_ID:
            name, made, residents = TODAY, entry.made, len(load_npcs(NPCS_DIR))
        else:
            cast = load_cast(self.root / id)
            name, made = id, entry.made or _made(self.root / id)
            residents = len(cast.residents) if cast else 0
        return World(
            id=id,
            name=entry.name or name,
            default=id == TODAY_ID,
            running=id == now,
            made=made,
            played=entry.played,
            day=saved.day if saved else None,
            time=saved.now if saved else None,
            player=player,
            residents=residents,
        )

    def _new_folder(self) -> Path:
        stem = datetime.now().strftime("%Y-%m-%d-%H%M")
        names = (stem if n == 1 else f"{stem}-{n}" for n in counting(1))
        while True:
            folder = self.root / next(names)
            if folder.exists():
                continue
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


def _folder(database: Path) -> Path | None:
    return None if str(database) == ":memory:" else database.parent


def _same(path: Path, other: Path) -> bool:
    return path.resolve() == other.resolve()


def _is_world(folder: Path) -> bool:
    from simile.casting import cast_npcs

    return not folder.is_symlink() and cast_npcs(folder) is not None


def _made(folder: Path) -> datetime:
    """When a world from before the index was made: its folder's name says, else its cast."""
    try:
        return datetime.strptime(folder.name[: len("2026-10-18-1432")], MADE_FORMAT).astimezone()
    except ValueError:
        return datetime.fromtimestamp((folder / "cast").stat().st_mtime).astimezone()


def _report(made: Cast, folder: Path, library: "Library", name: str | None = None) -> Made:
    env = {"SIMILE_DB": shown(folder / DATABASE)}
    if library.root != (folder / "library").resolve():
        env["SIMILE_LIBRARY"] = shown(library.root)
    return Made(
        id=folder.name,
        name=name or folder.name,
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
