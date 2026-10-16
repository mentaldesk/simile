import sys
import types
from collections.abc import Generator
from pathlib import Path

import pytest
from typer.testing import CliRunner

from simile.cli import create_cli
from simile.npc import load_npcs
from simile.protocol import SAMPLE_RATE
from simile.voice import rates
from simile.voice.measure import CALIBRATION, measure
from simile.voice.rates import (
    MeasuredRate,
    SpeakingRate,
    load_rates,
    outdated,
    save_rates,
    speaking_rate,
    voice_digest,
)

RESIDENTS = load_npcs()
TOBIAS = next(npc for npc in RESIDENTS if npc.id == "tobias")


class Steady:
    """Speaks every line in `base + per_word * words` seconds, in quarter-second chunks."""

    def __init__(self, base: float = 0.4, per_word: float = 0.32, **_: object) -> None:
        self.base, self.per_word = base, per_word
        self.voices: dict[str, Path] = {}

    def load(self) -> None:
        pass

    def add_voice(self, npc_id: str, clip: Path, transcript: str) -> None:
        self.voices[npc_id] = clip

    def generate(self, npc_id: str, sentence: str) -> Generator[bytes, None, None]:
        assert npc_id in self.voices
        samples = round((self.base + self.per_word * len(sentence.split())) * SAMPLE_RATE)
        for start in range(0, samples, SAMPLE_RATE // 4):
            yield bytes(2 * min(SAMPLE_RATE // 4, samples - start))


def test_a_rate_says_how_long_a_line_takes() -> None:
    rate = SpeakingRate(base_seconds=0.5, seconds_per_word=0.3)

    assert rate.seconds("One two  three four.") == pytest.approx(1.7)


def test_fits_a_rate_to_lines_and_their_lengths() -> None:
    spoken = [("One.", 0.7), ("One two three.", 1.3), ("One two three four five.", 1.9)]

    assert SpeakingRate.fit(spoken) == SpeakingRate(base_seconds=0.4, seconds_per_word=0.3)


def test_measures_a_voice_from_the_calibration_lines() -> None:
    synthesiser = Steady(base=0.45, per_word=0.33)

    measured = measure(synthesiser, TOBIAS)

    assert measured.rate == MeasuredRate(
        base_seconds=0.45, seconds_per_word=0.33, digest=voice_digest(TOBIAS.voice)
    )
    assert measured.error < 0.01
    assert synthesiser.voices == {"tobias": rates.REPO_ROOT / "content/voices/tobias.wav"}
    words = [len(line.split()) for line in CALIBRATION]
    assert len(words) >= 20 and min(words) == 1 and max(words) > 30


def test_a_voice_without_a_measurement_has_no_rate() -> None:
    assert speaking_rate("nobody") is None


def test_every_resident_with_a_voice_has_an_up_to_date_rate() -> None:
    stale = [npc.id for npc in outdated(RESIDENTS, load_rates())]

    command = f"uv run --extra voice simile voice measure {' '.join(stale)}"
    assert not stale, f"Measure their voices in server/: {command}"


def test_every_residents_rate_is_loaded() -> None:
    for npc in RESIDENTS:
        if npc.voice.reference_clip is not None:
            assert speaking_rate(npc.id) == load_rates()[npc.id]


def test_a_new_clip_or_transcript_makes_a_rate_outdated() -> None:
    rate = MeasuredRate(base_seconds=0.4, seconds_per_word=0.3, digest=voice_digest(TOBIAS.voice))
    retold = TOBIAS.model_copy(
        update={"voice": TOBIAS.voice.model_copy(update={"reference_line": "Something else."})}
    )
    unvoiced = TOBIAS.model_copy(
        update={"voice": TOBIAS.voice.model_copy(update={"reference_clip": None})}
    )

    assert outdated([TOBIAS], {"tobias": rate}) == []
    assert outdated([TOBIAS], {}) == [TOBIAS]
    assert outdated([retold], {"tobias": rate}) == [retold]
    assert outdated([unvoiced], {}) == []


def test_saves_and_loads_rates(tmp_path: Path) -> None:
    path = tmp_path / "rates.json"
    saved = {
        "kofi": MeasuredRate(base_seconds=0.5, seconds_per_word=0.29, digest="b"),
        "ana": MeasuredRate(base_seconds=-0.1, seconds_per_word=0.31, digest="a"),
    }

    save_rates(saved, path)

    assert load_rates(path) == saved
    assert list(load_rates(path)) == ["ana", "kofi"]
    assert load_rates(tmp_path / "missing.json") == {}


class TestMeasureCommand:
    runner = CliRunner()

    @pytest.fixture(autouse=True)
    def fake_voice(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
        path = tmp_path / "rates.json"
        monkeypatch.setattr(rates, "RATES", path)
        monkeypatch.setitem(
            sys.modules, "simile.voice.qwen", types.SimpleNamespace(QwenSynthesiser=Steady)
        )
        return path

    def run(self, *args: str) -> str:
        result = self.runner.invoke(create_cli(), ["voice", "measure", *args])
        assert result.exit_code == 0, result.output
        return result.output

    def test_measures_every_voice_without_a_rate(self, fake_voice: Path) -> None:
        output = self.run()

        measured = load_rates(fake_voice)
        voiced = [npc for npc in RESIDENTS if npc.voice.reference_clip is not None]
        assert list(measured) == sorted(npc.id for npc in voiced)
        assert outdated(voiced, measured) == []
        assert {(r.base_seconds, r.seconds_per_word) for r in measured.values()} == {(0.4, 0.32)}
        assert "tobias: 0.40 s + 0.320 s a word" in output

    def test_leaves_up_to_date_rates_alone(self, fake_voice: Path) -> None:
        current = MeasuredRate(
            base_seconds=0.1, seconds_per_word=0.2, digest=voice_digest(TOBIAS.voice)
        )
        save_rates({"tobias": current}, fake_voice)

        output = self.run("tobias")

        assert "up to date" in output
        assert load_rates(fake_voice) == {"tobias": current}

        self.run("tobias", "--force")

        assert load_rates(fake_voice)["tobias"].seconds_per_word == 0.32

    def test_remeasures_a_voice_that_changed_and_forgets_former_residents(
        self, fake_voice: Path
    ) -> None:
        stale = MeasuredRate(base_seconds=0.1, seconds_per_word=0.2, digest="old")
        save_rates({"tobias": stale, "ghost": stale}, fake_voice)

        self.run("tobias")

        assert load_rates(fake_voice) == {
            "tobias": MeasuredRate(
                base_seconds=0.4, seconds_per_word=0.32, digest=voice_digest(TOBIAS.voice)
            )
        }

    def test_refuses_an_unknown_resident(self) -> None:
        result = self.runner.invoke(create_cli(), ["voice", "measure", "nobody"])

        assert result.exit_code != 0
        assert "no such resident: nobody" in result.output
