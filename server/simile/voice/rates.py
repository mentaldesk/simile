import hashlib
import json
import statistics
from collections.abc import Iterable, Mapping
from functools import cache
from pathlib import Path

from pydantic import Field, TypeAdapter

from simile.schema import Id, Model, Npc, Voice
from simile.voice.service import REPO_ROOT

RATES = REPO_ROOT / "content" / "voices" / "rates.json"
SYNTHESIS = 2
"""Bump it when V1's synthesis changes how long lines take, so every rate has to be measured
again."""


class SpeakingRate(Model):
    """How long a voice takes to say a line: `base_seconds + seconds_per_word * words`."""

    base_seconds: float
    seconds_per_word: float = Field(gt=0)

    def seconds(self, text: str) -> float:
        return self.base_seconds + self.seconds_per_word * len(text.split())

    @classmethod
    def fit(cls, spoken: Iterable[tuple[str, float]]) -> "SpeakingRate":
        """The least-squares rate of (line, seconds of audio) pairs."""
        words, seconds = zip(*((len(text.split()), audio) for text, audio in spoken), strict=True)
        slope, intercept = statistics.linear_regression(words, seconds)
        return cls(base_seconds=round(intercept, 3), seconds_per_word=round(slope, 4))


class MeasuredRate(SpeakingRate):
    digest: str = Field(description="The `voice_digest` of the voice it was measured from.")


_rates_file = TypeAdapter(dict[Id, MeasuredRate])


def voice_digest(voice: Voice) -> str:
    """Changes whenever the voice's clip or transcript does, or `SYNTHESIS`."""
    if voice.reference_clip is None:
        raise ValueError("the voice has no reference clip")
    clip = (REPO_ROOT / voice.reference_clip).read_bytes()
    synthesis = f"synthesis {SYNTHESIS}\n".encode()
    return hashlib.sha256(synthesis + clip + voice.reference_line.encode()).hexdigest()


def outdated(npcs: Iterable[Npc], rates: Mapping[Id, MeasuredRate]) -> list[Npc]:
    """The NPCs with a voice that has no rate, or whose rate was measured from another voice."""
    return [
        npc
        for npc in npcs
        if npc.voice.reference_clip is not None
        and (npc.id not in rates or rates[npc.id].digest != voice_digest(npc.voice))
    ]


def load_rates(path: Path | None = None) -> dict[Id, MeasuredRate]:
    path = path or RATES
    return _rates_file.validate_json(path.read_bytes()) if path.exists() else {}


def save_rates(rates: Mapping[Id, MeasuredRate], path: Path | None = None) -> None:
    dumped = {id: rates[id].model_dump() for id in sorted(rates)}
    (path or RATES).write_text(json.dumps(dumped, indent=2) + "\n", encoding="utf-8")


@cache
def _measured() -> dict[Id, MeasuredRate]:
    return load_rates()


def speaking_rate(npc_id: Id) -> SpeakingRate | None:
    """The NPC's measured rate, or None for a voice nobody has measured."""
    return _measured().get(npc_id)
