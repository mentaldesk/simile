import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from simile.casting.model import Cast
from simile.memory import default_path
from simile.memory.store import DEFAULT_PATH

CAST_DIR = "cast"
MANIFEST = "cast.json"
NPCS_DIR = "npcs"
CONTENT_DIR = Path(__file__).resolve().parents[3] / "content"
SAVED_TABLES = ("saved_world", "memories", "relationships", "events", "flags")


class CastRefused(ValueError):
    """Writing a cast there would replace a village or something in content/."""


def data_directory() -> Path | None:
    """The folder that holds the save, `$SIMILE_DB`'s, or None for an in-memory one."""
    path = default_path()
    return None if str(path) == ":memory:" else path.parent


def cast_npcs(data: Path | None = None) -> Path | None:
    """The cast's folder of NPCs, if the data directory holds a cast."""
    data = data or data_directory()
    if data is None or not (data / CAST_DIR / MANIFEST).is_file():
        return None
    return data / CAST_DIR / NPCS_DIR


def load_cast(data: Path | None = None) -> Cast | None:
    data = data or data_directory()
    if data is None or not (path := data / CAST_DIR / MANIFEST).is_file():
        return None
    return Cast.model_validate_json(path.read_text(encoding="utf-8"))


def write_cast(cast: Cast, data: Path) -> Path:
    """Write the cast into the data directory, as its NPCs and a manifest, replacing a cast that
    never ran. Refuses where `check_writable` does."""
    check_writable(data)
    folder = data / CAST_DIR
    npcs = folder / NPCS_DIR
    if npcs.exists():
        shutil.rmtree(npcs)
    npcs.mkdir(parents=True)
    for npc in cast.npcs():
        (npcs / f"{npc.id}.json").write_text(npc.model_dump_json(indent=2) + "\n", encoding="utf-8")
    (folder / MANIFEST).write_text(cast.model_dump_json(indent=2) + "\n", encoding="utf-8")
    return folder


def check_writable(data: Path) -> None:
    """Refuse the default data directory, anywhere in content/, a data directory holding a save,
    and a `cast` folder that isn't a cast."""
    if _same(data, DEFAULT_PATH.parent):
        raise CastRefused(f"{data} holds today's village. Cast into a data directory of its own")
    if _within(data, CONTENT_DIR):
        raise CastRefused(f"{data} is in content/. Cast into a data directory of its own")
    if saved := [db.name for db in sorted(data.glob("*.db")) if holds_save(db)]:
        raise CastRefused(
            f"{data} already holds a saved village in {', '.join(saved)}. Cast into a new data "
            "directory, or forget that village first with `simile reset`"
        )
    folder = data / CAST_DIR
    if folder.exists() and not (folder / MANIFEST).is_file():
        raise CastRefused(f"{folder} is there and isn't a cast")


def holds_save(db: Path) -> bool:
    """Whether the database holds a village: a saved world, or anything R2 keeps. News alone
    isn't one. A file that isn't a database counts, to be safe."""
    try:
        uri = f"{db.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            tables = {
                name
                for (name,) in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'"
                )
            }
            return any(
                connection.execute(f"SELECT EXISTS (SELECT 1 FROM {table})").fetchone()[0]
                for table in SAVED_TABLES
                if table in tables
            )
    except sqlite3.DatabaseError:
        return True


def _same(path: Path, other: Path) -> bool:
    return _folded(path) == _folded(other)


def _within(path: Path, folder: Path) -> bool:
    return _folded(path).is_relative_to(_folded(folder))


def _folded(path: Path) -> Path:
    return Path(str(path.resolve()).casefold())
