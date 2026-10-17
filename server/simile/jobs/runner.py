import asyncio
import json
import logging
import math
import os
import re
import secrets
import shutil
import signal
import time
from collections import deque
from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, BinaryIO

from pydantic import BaseModel
from starlette.applications import Starlette

from simile.jobs.capabilities import needs
from simile.jobs.report import PREFIX

logger = logging.getLogger(__name__)

CONTENT = Path(__file__).resolve().parents[3] / "content"
DEFAULT_ROOT = Path(__file__).resolve().parents[2] / "data" / "jobs"
FILES = "/api/jobs/files"
NAME = re.compile(r"[a-z][a-z0-9_]*")
JOB_ID = re.compile(r"[0-9a-f]{16}")
WAITING = 4
KEEP = 100
GRACE = 5.0
TAIL = 20
CHUNK = 64 * 1024
LINE_KEPT = 4096
MESSAGE_LIMIT = 200
DRAIN = 1.0
POLL = 0.05
LEFTOVER_AGE = 24 * 60 * 60


class State(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"

    @property
    def finished(self) -> bool:
        return self in (State.SUCCEEDED, State.FAILED, State.CANCELLED)


class Job(BaseModel):
    id: str
    kind: str
    state: State = State.QUEUED
    progress: float = 0.0
    message: str = ""
    error: str | None = None
    result: dict[str, Any] | None = None
    created: datetime
    started: datetime | None = None
    finished: datetime | None = None


@dataclass(frozen=True)
class Kind[P: BaseModel]:
    """`command` runs in `work`; on success `publish` moves its outputs into `out`."""

    name: str
    params: type[P]
    command: Callable[[P, Path], Sequence[str]]
    publish: Callable[[P, Path, Path], dict[str, Any]]
    requires: tuple[str, ...] = ()
    files: str = ""


class UnknownKind(LookupError):
    pass


class Busy(RuntimeError):
    pass


class Finished(RuntimeError):
    pass


class Failed(RuntimeError):
    pass


def url(kind: str, name: str) -> str:
    return f"{FILES}/{kind}/{name}"


def outside_content(path: Path) -> Path:
    resolved = path.resolve()
    if resolved.is_relative_to(CONTENT.resolve()):
        raise ValueError(f"{resolved} is inside content/, which jobs never write to")
    return resolved


@dataclass
class Entry:
    job: Job
    changed: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[None] | None = None


class Jobs:
    """Runs each job as a subprocess, one at a time per kind, writing only under `root`."""

    def __init__(
        self,
        root: Path,
        found: Mapping[str, bool],
        *,
        waiting: int = WAITING,
        keep: int = KEEP,
        grace: float = GRACE,
    ) -> None:
        self.root = outside_content(root)
        outside_content(self.root / "work")
        self.found = dict(found)
        self.waiting, self.keep, self.grace = waiting, keep, grace
        self._kinds: dict[str, Kind[Any]] = {}
        self._entries: dict[str, Entry] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    def register(self, kind: Kind[Any]) -> Callable[[], None]:
        if not NAME.fullmatch(kind.name) or kind.name == "work":
            raise ValueError(f"{kind.name!r} can't be a job kind")
        if kind.name in self._kinds:
            raise ValueError(f"there's already a {kind.name} job kind")
        outside_content(self.root / kind.name)
        self._kinds[kind.name] = kind

        def unregister() -> None:
            self._kinds.pop(kind.name, None)

        return unregister

    def missing(self, kind: Kind[Any]) -> str | None:
        absent = [needs(name) for name in kind.requires if not self.found.get(name, False)]
        if not absent:
            return None
        return f"{kind.name} jobs need {' and '.join(absent)}, which this machine doesn't have"

    def capabilities(self) -> dict[str, Any]:
        kinds = {}
        for name, kind in self._kinds.items():
            reason = self.missing(kind)
            kinds[name] = {"available": reason is None, "reason": reason}
        return {"machine": dict(self.found), "kinds": kinds}

    def submit(self, kind_name: str, params: Any) -> Job:
        """Queues a job, or fails it at once if this machine can't run its kind."""
        kind = self._kinds.get(kind_name)
        if kind is None:
            raise UnknownKind(f"there's no {kind_name!r} job")
        parsed = kind.params.model_validate(params)
        unfinished = sum(
            1
            for entry in self._entries.values()
            if entry.job.kind == kind.name and not entry.job.state.finished
        )
        if unfinished > self.waiting:
            raise Busy(f"{unfinished - 1} {kind.name} jobs are already waiting")
        entry = Entry(Job(id=secrets.token_hex(8), kind=kind.name, created=datetime.now(UTC)))
        self._entries[entry.job.id] = entry
        if (reason := self.missing(kind)) is not None:
            self._end(entry, State.FAILED, error=reason)
        else:
            entry.task = asyncio.create_task(self._run(entry, kind, parsed))
            entry.task.add_done_callback(lambda _: self._settle(entry))
        return entry.job.model_copy(deep=True)

    def get(self, job_id: str) -> Job | None:
        entry = self._entries.get(job_id)
        return None if entry is None else entry.job.model_copy(deep=True)

    def list(self) -> list[Job]:
        return [entry.job.model_copy(deep=True) for entry in self._entries.values()]

    async def cancel(self, job_id: str) -> Job:
        """Stops a queued or running job and waits for it. Raises `KeyError` or `Finished`."""
        entry = self._entries[job_id]
        if entry.task is None:
            raise Finished(f"the job has already {entry.job.state}")
        task = entry.task
        _cancel(task)
        await asyncio.wait([task])
        return entry.job.model_copy(deep=True)

    async def watch(self, job_id: str) -> AsyncIterator[Job]:
        """The job now and after each change, until it has finished."""
        entry = self._entries.get(job_id)
        while entry is not None:
            changed = entry.changed
            yield entry.job.model_copy(deep=True)
            if entry.job.state.finished:
                return
            await changed.wait()

    def remove_leftovers(self) -> None:
        """Deletes the work directories, untouched for a day, that a killed server left behind."""
        work = self.root / "work"
        if not work.is_dir():
            return
        for path in work.iterdir():
            if not JOB_ID.fullmatch(path.name) or path.name in self._entries:
                continue
            with suppress(FileNotFoundError):
                if time.time() - path.stat().st_mtime > LEFTOVER_AGE:
                    shutil.rmtree(path, ignore_errors=True)

    def file(self, kind_name: str, name: str) -> Path | None:
        """A file a job of this kind published, if `name` is one it may publish."""
        kind = self._kinds.get(kind_name)
        if kind is None or not kind.files or not re.fullmatch(kind.files, name):
            return None
        out = self.root / kind.name
        path = (out / name).resolve()
        return path if path.parent == out.resolve() and path.is_file() else None

    async def close(self) -> None:
        tasks = [entry.task for entry in self._entries.values() if entry.task is not None]
        for task in tasks:
            _cancel(task)
        if tasks:
            await asyncio.wait(tasks)

    async def _run(self, entry: Entry, kind: Kind[Any], params: BaseModel) -> None:
        async with self._locks.setdefault(kind.name, asyncio.Lock()):
            work = self.root / "work" / entry.job.id
            try:
                work.mkdir(parents=True)
                (work / "params.json").write_text(params.model_dump_json())
                self._update(entry, state=State.RUNNING, started=datetime.now(UTC))
                await self._execute(entry, kind.command(params, work), work)
                out = self.root / kind.name
                out.mkdir(parents=True, exist_ok=True)
                result = kind.publish(params, work, out)
                self._end(entry, State.SUCCEEDED, progress=1.0, result=result)
            except Failed as failure:
                self._end(entry, State.FAILED, error=str(failure))
            except Exception as error:
                logger.exception(f"{kind.name} job {entry.job.id} failed")
                self._end(entry, State.FAILED, error=f"{type(error).__name__}: {error}")
            finally:
                shutil.rmtree(work, ignore_errors=True)

    async def _execute(self, entry: Entry, command: Sequence[str], work: Path) -> None:
        # Our own pipe, so a stray child holding it open can't stop process.wait() returning.
        read_end, write_end = os.pipe()
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                cwd=work,
                stdin=asyncio.subprocess.DEVNULL,
                stdout=write_end,
                stderr=write_end,
                start_new_session=True,
            )
        except OSError as error:
            os.close(read_end)
            raise Failed(f"couldn't start {command[0]}: {error.strerror or error}") from None
        except BaseException:
            os.close(read_end)
            raise
        finally:
            os.close(write_end)
        output = os.fdopen(read_end, "rb", buffering=0)
        tail: deque[str] = deque(maxlen=TAIL)
        reading = asyncio.create_task(self._read(entry, output, tail))
        try:
            code = await process.wait()
        finally:
            await self._stop(process)
            with suppress(TimeoutError):
                await asyncio.wait_for(reading, DRAIN)
            output.close()
        if code != 0:
            lines = "".join(f"\n{line}" for line in tail)
            raise Failed(f"the {entry.job.kind} job exited with code {code}{lines}")

    async def _read(self, entry: Entry, output: BinaryIO, tail: deque[str]) -> None:
        reader = asyncio.StreamReader()
        transport, _ = await asyncio.get_running_loop().connect_read_pipe(
            lambda: asyncio.StreamReaderProtocol(reader), output
        )
        try:
            line = b""
            while chunk := await reader.read(CHUNK):
                *ended, rest = chunk.split(b"\n")
                for piece in ended:
                    self._line(entry, (line + piece)[:LINE_KEPT], tail)
                    line = b""
                line = (line + rest)[:LINE_KEPT]
            if line:
                self._line(entry, line, tail)
        finally:
            transport.close()

    def _line(self, entry: Entry, raw: bytes, tail: deque[str]) -> None:
        line = raw.decode(errors="replace").rstrip()
        if not self._report(entry, line):
            tail.append(line)

    async def _stop(self, process: asyncio.subprocess.Process) -> None:
        """Ends what's left of the job's process group: SIGTERM, then SIGKILL after `grace`."""
        try:
            if _signal(process.pid, signal.SIGTERM):
                deadline = time.monotonic() + self.grace
                while _signal(process.pid, 0) and time.monotonic() < deadline:
                    await asyncio.sleep(POLL)
        finally:
            _signal(process.pid, signal.SIGKILL)
        await process.wait()

    def _report(self, entry: Entry, line: str) -> bool:
        if not line.startswith(PREFIX):
            return False
        try:
            report = json.loads(line[len(PREFIX) :])
            fraction = float(report["progress"])
            message = str(report.get("message", ""))[:MESSAGE_LIMIT]
        except (ValueError, KeyError, TypeError):
            return False
        if not math.isfinite(fraction):
            return False
        self._update(entry, progress=min(max(fraction, 0.0), 1.0), message=message)
        return True

    def _settle(self, entry: Entry) -> None:
        if not entry.job.state.finished:
            self._end(entry, State.CANCELLED)

    def _update(self, entry: Entry, **fields: Any) -> None:
        for name, value in fields.items():
            setattr(entry.job, name, value)
        changed, entry.changed = entry.changed, asyncio.Event()
        changed.set()

    def _end(self, entry: Entry, state: State, **fields: Any) -> None:
        entry.task = None
        self._update(entry, state=state, finished=datetime.now(UTC), **fields)
        finished = sorted(
            (e for e in self._entries.values() if e.job.state.finished),
            key=lambda e: e.job.finished or e.job.created,
        )
        for old in finished[: max(0, len(finished) - self.keep)]:
            del self._entries[old.job.id]


def _signal(group: int, number: int) -> bool:
    try:
        os.killpg(group, number)
    except (ProcessLookupError, PermissionError):
        return False
    return True


def _cancel(task: asyncio.Task[None]) -> None:
    # A second cancel would interrupt the first one's cleanup and leave its subprocess running.
    if not task.cancelling():
        task.cancel()


def jobs_of(app: Starlette) -> Jobs:
    """The server's jobs on `app.state.jobs`, created on first use."""
    if not hasattr(app.state, "jobs"):
        from simile.jobs.capabilities import detect

        app.state.jobs = Jobs(Path(os.environ.get("SIMILE_JOBS") or DEFAULT_ROOT), detect())
    return app.state.jobs
