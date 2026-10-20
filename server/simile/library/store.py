import logging
import os
import re
import secrets
import threading
from collections.abc import Mapping
from datetime import UTC, datetime
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any

from pydantic import ValidationError
from starlette.applications import Starlette

from simile.library.archive import Refused, check_clip, pack, reasons, unpack
from simile.schema import PLAYER_ID, Appearance, Character, CharacterSource, Model

if TYPE_CHECKING:
    from simile.characters.novelty import Embedder, Match, Novelty

logger = logging.getLogger(__name__)

REPO = Path(__file__).resolve().parents[3]
CONTENT = REPO / "content"
DEFAULT_ROOT = REPO / "server" / "data" / "library"
ID = re.compile(r"[a-z][a-z0-9_]{0,63}")


class NotFound(LookupError):
    pass


class ReadOnly(Exception):
    pass


class PlayerLook(Model):
    appearance: Appearance


def default_root() -> Path:
    """`$SIMILE_LIBRARY`, else `library/` beside the database (`$SIMILE_DB`)."""
    from simile.memory.store import default_path

    if root := os.environ.get("SIMILE_LIBRARY"):
        return Path(root)
    database = default_path()
    return DEFAULT_ROOT if str(database) == ":memory:" else database.parent / "library"


def within(path: Path, folder: Path) -> bool:
    """Whether `path` is `folder` or inside it, also on a disk that ignores case."""
    resolved, parent = (Path(str(p.resolve()).casefold()) for p in (path, folder))
    return resolved.is_relative_to(parent)


class Library:
    """The premade characters in `premade`, which are read-only, and the player's own in `root`."""

    def __init__(
        self, root: Path, premade: Path | None = None, *, embedder: "Embedder | None" = None
    ) -> None:
        if within(root, CONTENT):
            raise ValueError(f"{root} is in content/, and player characters never go there")
        self.root = root.resolve()
        self.premade_dir = premade
        self.embedder = embedder
        self.generating = 0
        self._lock = threading.RLock()
        self._novelty_lock = threading.Lock()
        self._novelty: tuple[tuple[Any, ...], Novelty] | None = None

    @property
    def characters_dir(self) -> Path:
        return self.root / "characters"

    @property
    def clips_dir(self) -> Path:
        return self.root / "clips"

    @cached_property
    def premade(self) -> dict[str, Character]:
        from simile.characters.pool import POOL_DIR, load_pool

        return {c.id: c for c in load_pool(self.premade_dir or POOL_DIR)}

    def is_premade(self, id: str) -> bool:
        return id in self.premade

    def characters(self) -> list[Character]:
        """Premade characters, then the player's, each by name."""
        premade = sorted(self.premade.values(), key=lambda c: c.name)
        return premade + sorted(self.player_characters(), key=lambda c: c.name)

    def player_characters(self) -> list[Character]:
        found = []
        for path in sorted(self.characters_dir.glob("*.json")):
            character = self._load(path)
            if character is not None and character.id not in self.premade:
                found.append(character)
        return found

    def ids(self) -> set[str]:
        return set(self.premade) | {path.stem for path in self.characters_dir.glob("*.json")}

    def get(self, id: str) -> Character:
        if id in self.premade:
            return self.premade[id]
        path = self._path(id)
        character = self._load(path) if path.is_file() else None
        if character is None:
            raise NotFound(id)
        return character

    def create(self, data: Mapping[str, Any]) -> Character:
        """Saves a new player character, with a new id if another player character has its id."""
        _object(data)
        with self._lock:
            now = datetime.now(UTC)
            character = _validated(data, created=now, updated=now, version=1)
            if character.id in self.premade:
                raise ReadOnly("Premade characters are read-only")
            id = self._free_id(character.id)
            self._clip_path(id).unlink(missing_ok=True)
            return self._save(character.model_copy(update={"id": id}), clip=False)

    def update(self, id: str, data: Mapping[str, Any]) -> Character:
        _object(data)
        with self._lock:
            old = self._own(id)
            if data.get("id", id) != id:
                raise Refused("A character's id can't change")
            character = _validated(
                {**data, "id": id},
                created=old.created,
                updated=max(datetime.now(UTC), old.updated),
                version=old.version + 1,
            )
            return self._save(character, clip=self._clip_path(id).is_file())

    def delete(self, id: str) -> None:
        with self._lock:
            self._own(id)
            self._path(id).unlink()
            self._clip_path(id).unlink(missing_ok=True)

    def clip(self, character: Character) -> Path | None:
        """The character's reference clip: under the repo for a premade one, else in `root`."""
        if character.voice.reference_clip is None:
            return None
        if character.source is CharacterSource.PREMADE:
            return REPO / character.voice.reference_clip
        return self._clip_path(character.id)

    def save_clip(self, id: str, clip: bytes) -> Character:
        """Gives a player character `clip` as its reference clip, once it decodes."""
        check_clip(clip)
        with self._lock:
            old = self._own(id)
            self._write(self._clip_path(id), clip)
            update = {"updated": max(datetime.now(UTC), old.updated), "version": old.version + 1}
            return self._save(old.model_copy(update=update), clip=True)

    def export(self, id: str) -> bytes:
        character = self.get(id)
        if character.id in self.premade:
            raise ReadOnly("Premade characters can't be exported")
        path = self.clip(character)
        return pack(character, path.read_bytes() if path and path.is_file() else None)

    def import_file(self, data: bytes) -> Character:
        """Saves the character in an exported file as a player's, with a new id if it's taken."""
        character, clip = unpack(data)
        with self._lock:
            now = datetime.now(UTC)
            fields = character.model_dump() | {
                "id": self._free_id(character.id),
                "created": min(character.created, now),
                "updated": min(character.updated, now),
            }
            try:
                imported = _validated(fields)
            except ValidationError as error:
                raise Refused(f"The character isn't valid as of today: {reasons(error)}") from None
            if clip is None:
                self._clip_path(imported.id).unlink(missing_ok=True)
            else:
                self._write(self._clip_path(imported.id), clip)
            return self._save(imported, clip=clip is not None)

    def player(self) -> Appearance:
        """The player's look, or the built-in one until they choose their own."""
        path = self.root / "player.json"
        if path.is_file() and path.resolve().is_relative_to(self.root):
            try:
                return PlayerLook.model_validate_json(path.read_bytes()).appearance
            except ValidationError:
                logger.warning("Ignoring %s, which isn't a valid look", path)
        from simile.characters.palette import PLAYER

        return PLAYER

    def save_player(self, appearance: Appearance) -> Appearance:
        look = PlayerLook(appearance=appearance)
        self._write(self.root / "player.json", (look.model_dump_json(indent=2) + "\n").encode())
        return appearance

    def too_close(self, character: Character) -> "Match | None":
        """The library character `character` is a near-copy of, if any. Loads a model, so slow."""
        from simile.characters.novelty import LocalEmbedder, Novelty

        with self._novelty_lock:
            library = self.characters()
            key = tuple((c.id, c.version, c.updated) for c in library)
            if self._novelty is None or self._novelty[0] != key:
                self.embedder = self.embedder or LocalEmbedder()
                self._novelty = (key, Novelty(self.embedder, library))
            return self._novelty[1].too_close(character)

    def _own(self, id: str) -> Character:
        if id in self.premade:
            raise ReadOnly("Premade characters are read-only")
        return self.get(id)

    def _path(self, id: str) -> Path:
        if not ID.fullmatch(id) or id == PLAYER_ID:
            raise NotFound(id)
        return self.characters_dir / f"{id}.json"

    def _clip_path(self, id: str) -> Path:
        self._path(id)
        return self.clips_dir / f"{id}.wav"

    def _free_id(self, id: str) -> str:
        from simile.characters.generate import character_id

        taken = self.ids()
        return id if id not in taken else character_id(id, taken)

    def _load(self, path: Path) -> Character | None:
        if not path.resolve().is_relative_to(self.root):
            logger.warning("Ignoring %s, which leads out of the library", path)
            return None
        try:
            character = Character.model_validate_json(path.read_bytes())
        except ValidationError as error:
            logger.warning("Ignoring %s, which isn't a valid character: %s", path, error)
            return None
        if character.id != path.stem or character.source is not CharacterSource.PLAYER:
            logger.warning("Ignoring %s, which isn't a player character with that id", path)
            return None
        return character

    def _save(self, character: Character, *, clip: bool) -> Character:
        reference = f"clips/{character.id}.wav" if clip else None
        voice = character.voice.model_copy(update={"reference_clip": reference})
        saved = character.model_copy(update={"voice": voice})
        self._write(self._path(saved.id), (saved.model_dump_json(indent=2) + "\n").encode())
        return saved

    def _write(self, path: Path, data: bytes) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        if not path.parent.resolve().is_relative_to(self.root):
            raise Refused(f"{path.parent} leads out of the library")
        temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.tmp")
        try:
            temporary.write_bytes(data)
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def _object(data: Any) -> None:
    if not isinstance(data, Mapping):
        raise Refused("A character must be a JSON object")


def _validated(data: Mapping[str, Any], **fields: Any) -> Character:
    return Character.model_validate({**data, **fields, "source": CharacterSource.PLAYER})


def library_of(app: Starlette) -> Library:
    """The server's library on `app.state.library`, created on first use."""
    if not hasattr(app.state, "library"):
        app.state.library = Library(default_root())
    return app.state.library
