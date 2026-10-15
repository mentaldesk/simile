import threading
from collections import Counter
from collections.abc import Generator
from pathlib import Path


class FakeSynthesiser:
    """For tests: instant PCM chunks. `gate()` holds a sentence; sentences in `failing` raise."""

    def __init__(self, chunks: int = 4) -> None:
        self.chunks = chunks
        self.loaded = False
        self.threads: set[str] = set()
        self.voices: dict[str, tuple[Path, str]] = {}
        self.started: list[str] = []
        self.made: Counter[str] = Counter()
        self.closed: list[str] = []
        self.gates: dict[str, threading.Semaphore] = {}
        self.failing: set[str] = set()

    @staticmethod
    def chunk(index: int) -> bytes:
        return index.to_bytes(2, "little") * 240

    def gate(self, sentence: str) -> threading.Semaphore:
        self.gates[sentence] = threading.Semaphore(0)
        return self.gates[sentence]

    def open_gates(self) -> None:
        for gate in self.gates.values():
            gate.release(self.chunks)

    def load(self) -> None:
        self.threads.add(threading.current_thread().name)
        self.loaded = True

    def add_voice(self, npc_id: str, clip: Path, transcript: str) -> None:
        self.threads.add(threading.current_thread().name)
        self.voices[npc_id] = (clip, transcript)

    def generate(self, npc_id: str, sentence: str) -> Generator[bytes, None, None]:
        self.threads.add(threading.current_thread().name)
        self.started.append(sentence)
        try:
            for index in range(self.chunks):
                if gate := self.gates.get(sentence):
                    gate.acquire(timeout=5)
                if sentence in self.failing:
                    raise RuntimeError(f"failed to say {sentence!r}")
                self.made[sentence] += 1
                yield self.chunk(index)
        finally:
            self.closed.append(sentence)
