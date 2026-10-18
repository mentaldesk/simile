"""Recordings sent to the server, which are checked before a voice check job reads them."""

import asyncio
import secrets
import time
from contextlib import suppress
from pathlib import Path

from starlette.applications import Starlette

from simile.jobs import Finished, Jobs
from simile.library import Refused
from simile.library.archive import MAX_CLIP, check_clip

MAX_UPLOAD = MAX_CLIP
STALE = 24 * 60 * 60


class Unsupported(ValueError):
    pass


def suffix(data: bytes) -> str:
    if data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return ".wav"
    if data[:3] == b"ID3" or (len(data) > 1 and data[0] == 0xFF and data[1] & 0xE0 == 0xE0):
        return ".mp3"
    if data[4:8] == b"ftyp":
        return ".m4a"
    if data[:4] == b"\x1aE\xdf\xa3":
        raise Unsupported("WebM recordings aren't supported: send a WAV, MP3 or M4A file")
    raise Unsupported("A recording has to be a WAV, MP3 or M4A file")


def check(data: bytes) -> str:
    """The suffix to store an upload with, or `Refused` or `Unsupported` with the reason."""
    if not data:
        raise Refused("The recording is empty")
    found = suffix(data)
    if found == ".wav":
        check_clip(data)
    return found


def store(folder: Path, data: bytes, found: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{secrets.token_hex(16)}{found}"
    path.write_bytes(data)
    return path


def remove_stale(folder: Path) -> None:
    """Deletes uploads a day old, which no job will read now."""
    if not folder.is_dir():
        return
    for path in folder.iterdir():
        with suppress(FileNotFoundError):
            if path.is_file() and time.time() - path.stat().st_mtime > STALE:
                path.unlink()


class Waiting:
    """Uploads waiting for their check jobs, each deleted once its job has finished."""

    def __init__(self) -> None:
        self._watchers: dict[str, asyncio.Task[None]] = {}

    def add(self, jobs: Jobs, job_id: str, path: Path) -> None:
        watcher = asyncio.create_task(self._remove_when_done(jobs, job_id, path))
        self._watchers[job_id] = watcher
        watcher.add_done_callback(lambda _: self._watchers.pop(job_id, None))

    async def close(self, jobs: Jobs) -> None:
        for job_id in list(self._watchers):
            with suppress(KeyError, Finished):
                await jobs.cancel(job_id)
        await asyncio.gather(*self._watchers.values(), return_exceptions=True)

    @staticmethod
    async def _remove_when_done(jobs: Jobs, job_id: str, path: Path) -> None:
        async for _ in jobs.watch(job_id):
            pass
        path.unlink(missing_ok=True)


def waiting_of(app: Starlette) -> Waiting:
    if not hasattr(app.state, "voice_uploads"):
        app.state.voice_uploads = Waiting()
    return app.state.voice_uploads
