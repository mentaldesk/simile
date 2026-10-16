import logging
import zlib
from collections.abc import Generator
from pathlib import Path

import mlx.core as mx
from mlx_audio.tts.models.base import GenerationResult
from mlx_audio.tts.utils import load_model
from mlx_audio.utils import load_audio

from simile.voice.silence import LeadingSilence

logger = logging.getLogger(__name__)

MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
TOKENS_PER_SECOND = 12.5
CHUNK_SECONDS = 0.25


def to_pcm(audio: mx.array) -> bytes:
    return bytes(memoryview((mx.clip(audio, -1, 1) * 32767).round().astype(mx.int16)))


class QwenSynthesiser:
    """Qwen3-TTS voice cloning on MLX, so Apple Silicon only. A seed makes sentences repeatable."""

    def __init__(self, model: str = MODEL, seed: int | None = None) -> None:
        self._model_name = model
        self._seed = seed
        self._references: dict[str, tuple[mx.array, str]] = {}

    def load(self) -> None:
        self._model = load_model(self._model_name)

    def add_voice(self, npc_id: str, clip: Path, transcript: str) -> None:
        audio = load_audio(str(clip), sample_rate=self._model.sample_rate)
        self._references[npc_id] = (audio, transcript)
        # mlx-audio caches the encoded reference by its contents on first use.
        for _ in self._generate(npc_id, "Hello.", max_tokens=1):
            pass

    # Bump rates.SYNTHESIS when a change here alters how long lines take.
    def generate(self, npc_id: str, sentence: str) -> Generator[bytes, None, None]:
        # Caps a generation that never emits end-of-speech.
        max_seconds = 3 + len(sentence) / 5
        max_tokens = int(TOKENS_PER_SECOND * max_seconds)
        if self._seed is not None:
            mx.random.seed(zlib.crc32(f"{self._seed}/{npc_id}/{sentence}".encode()))
        tokens = 0
        silence = LeadingSilence()
        for result in self._generate(npc_id, sentence, max_tokens):
            tokens += result.token_count
            yield silence.feed(to_pcm(result.audio))
        yield silence.end()
        if tokens >= max_tokens:
            logger.warning(f"Cut {npc_id} off after {max_seconds:.1f}s of {sentence!r}")

    def _generate(
        self, npc_id: str, sentence: str, max_tokens: int
    ) -> Generator[GenerationResult, None, None]:
        audio, transcript = self._references[npc_id]
        yield from self._model.generate(
            text=sentence,
            lang_code="english",
            ref_audio=audio,
            ref_text=transcript,
            stream=True,
            streaming_interval=CHUNK_SECONDS,
            max_tokens=max_tokens,
        )
