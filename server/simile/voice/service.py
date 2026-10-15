import asyncio
import itertools
import threading
from collections.abc import AsyncGenerator, Callable, Generator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass, field
from enum import IntEnum
from pathlib import Path
from typing import Protocol, Self

from starlette.applications import Starlette

from simile.schema import Voice

REPO_ROOT = Path(__file__).resolve().parents[3]


class Priority(IntEnum):
    PLAYER = 0
    OVERHEARD = 1


class Synthesiser(Protocol):
    """Blocking text to speech. VoiceService only ever calls it from its one voice thread."""

    def load(self) -> None: ...

    def add_voice(self, npc_id: str, clip: Path, transcript: str) -> None: ...

    def generate(self, npc_id: str, sentence: str) -> Generator[bytes, None, None]:
        """24 kHz mono 16-bit little-endian PCM, in chunks of whole samples."""
        ...


@dataclass
class _Job:
    npc_id: str
    sentence: str
    chunks: asyncio.Queue[bytes | None] = field(default_factory=asyncio.Queue)
    cancelled: threading.Event = field(default_factory=threading.Event)
    error: Exception | None = None


class VoiceService:
    """Speaks one sentence at a time, highest priority first, then in the order asked."""

    def __init__(self, synthesiser: Synthesiser) -> None:
        self._synthesiser = synthesiser
        self._thread = ThreadPoolExecutor(max_workers=1, thread_name_prefix="simile-voice")
        self._queue: asyncio.PriorityQueue[tuple[Priority, int, _Job]] = asyncio.PriorityQueue()
        self._order = itertools.count()
        self._voices: set[str] = set()
        self._worker: asyncio.Task[None] | None = None

    async def __aenter__(self) -> Self:
        await self._run(self._synthesiser.load)
        self._worker = asyncio.create_task(self._work())
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        if self._worker:
            self._worker.cancel()
            await asyncio.gather(self._worker, return_exceptions=True)
        while not self._queue.empty():
            *_, job = self._queue.get_nowait()
            job.chunks.put_nowait(None)
        self._thread.shutdown(wait=False)

    async def add_voice(self, npc_id: str, voice: Voice) -> None:
        """Load and encode the NPC's reference clip once, ahead of their first line."""
        if voice.reference_clip is None:
            raise ValueError(f"{npc_id} has no reference clip")
        clip = REPO_ROOT / voice.reference_clip
        await self._run(self._synthesiser.add_voice, npc_id, clip, voice.reference_line)
        self._voices.add(npc_id)

    def has_voice(self, npc_id: str) -> bool:
        return npc_id in self._voices

    def speak(
        self, npc_id: str, sentence: str, priority: Priority = Priority.OVERHEARD
    ) -> AsyncGenerator[bytes, None]:
        """The sentence's audio. It joins the queue when iteration starts; closing it cancels."""
        if npc_id not in self._voices:
            raise KeyError(f"no voice for {npc_id}")
        return self._stream(_Job(npc_id, sentence), priority)

    async def _stream(self, job: _Job, priority: Priority) -> AsyncGenerator[bytes, None]:
        self._queue.put_nowait((priority, next(self._order), job))
        try:
            while (pcm := await job.chunks.get()) is not None:
                yield pcm
            if job.error:
                raise job.error
        finally:
            job.cancelled.set()

    async def _work(self) -> None:
        loop = asyncio.get_running_loop()
        while True:
            *_, job = await self._queue.get()
            if job.cancelled.is_set():
                continue
            try:
                await loop.run_in_executor(self._thread, self._generate, job, loop)
            except asyncio.CancelledError:
                job.cancelled.set()
                raise
            except Exception as error:
                job.error = error
            finally:
                job.chunks.put_nowait(None)

    def _generate(self, job: _Job, loop: asyncio.AbstractEventLoop) -> None:
        with closing(self._synthesiser.generate(job.npc_id, job.sentence)) as chunks:
            for pcm in chunks:
                if job.cancelled.is_set():
                    return
                loop.call_soon_threadsafe(job.chunks.put_nowait, pcm)

    async def _run(self, function: Callable[..., None], *args: object) -> None:
        await asyncio.get_running_loop().run_in_executor(self._thread, function, *args)


def voice_of(app: Starlette) -> VoiceService | None:
    """The server's voice service, or None when it runs unvoiced."""
    return getattr(app.state, "voice", None)
