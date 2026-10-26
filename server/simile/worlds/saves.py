import json
import sqlite3
from contextlib import closing
from datetime import UTC, datetime
from pathlib import Path
from typing import NamedTuple


class Progress(NamedTuple):
    now: datetime
    day: int


def progress(database: Path) -> Progress | None:
    """How far the world saved in `database` has got: its sim time, and which day that is, from
    the first day anything happened. None if it holds no save."""
    if not database.is_file():
        return None
    try:
        with closing(sqlite3.connect(f"{database.resolve().as_uri()}?mode=ro", uri=True)) as db:
            row = db.execute("SELECT data FROM saved_world").fetchone()
            if row is None:
                return None
            now = datetime.fromisoformat(json.loads(row[0])["now"]).astimezone(UTC)
            began = min(
                (t for (t,) in db.execute(FIRST) if t is not None),
                default=now.timestamp(),
            )
    except (sqlite3.Error, KeyError, ValueError, TypeError):
        return None
    first = datetime.fromtimestamp(began, UTC)
    return Progress(now=now, day=max(1, (now.date() - first.date()).days + 1))


FIRST = """
SELECT min(time) FROM events
UNION ALL SELECT min(time) FROM saved_ledger
"""
