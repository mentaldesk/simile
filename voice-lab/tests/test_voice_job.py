import json
import shutil
import wave
from pathlib import Path

import pytest

from import_voices import SAMPLE_RATE, ConversionError
from voice_job import check_recording

LINE = "The early bus leaves at twenty to seven, and I like to be at the stop by half past."


def write_wav(path: Path, seconds: float) -> None:
    with wave.open(str(path), "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(SAMPLE_RATE)
        writer.writeframes(bytes(2 * int(seconds * SAMPLE_RATE)))


class FakeTools:
    def __init__(self, heard: str = LINE, accent: str = "scotland 90%") -> None:
        self.heard, self.accent = heard, accent

    def convert(self, source: Path, wav: Path) -> None:
        if source.read_bytes()[:4] != b"RIFF":
            raise ConversionError("Couldn't open input file")
        shutil.copyfile(source, wav)

    def transcribe(self, wav: Path) -> str:
        return self.heard

    def clone(self, wav: Path, transcript: str, out: Path) -> list[Path]:
        out.mkdir(parents=True, exist_ok=True)
        paths = [out / f"{wav.stem}_{n}.wav" for n in (1, 2, 3)]
        for path in paths:
            write_wav(path, 3.0)
        return paths

    def accents(self, wavs: list[Path]) -> dict[str, str]:
        return {str(wav): self.accent for wav in wavs}


@pytest.fixture
def work(tmp_path: Path) -> Path:
    work = tmp_path / "work"
    work.mkdir()
    (work / "params.json").write_text(json.dumps({"upload": "x.wav", "reference_line": f"  {LINE}\n"}))
    return work


def result(work: Path) -> dict:
    return json.loads((work / "result.json").read_text())


def test_checks_a_recording_in_the_work_directory(work: Path, tmp_path: Path) -> None:
    upload = tmp_path / "abc.WAV"
    write_wav(upload, 8.0)

    check_recording(work, upload, FakeTools())

    assert not upload.exists()
    assert (work / "recording.wav").read_bytes() == (work / "upload.wav").read_bytes()
    assert sorted(path.name for path in (work / "samples").iterdir()) == [
        "recording_1.wav",
        "recording_2.wav",
        "recording_3.wav",
    ]
    assert result(work) == {
        "seconds": 8.0,
        "heard": LINE,
        "word_error_rate": 0.0,
        "accent": "scotland 90%",
        "sample_accents": ["scotland 90%"] * 3,
        "errors": [],
        "problems": [],
        "warnings": [],
    }


def test_reports_a_recording_that_says_something_else(work: Path, tmp_path: Path) -> None:
    upload = tmp_path / "abc.wav"
    write_wav(upload, 8.0)

    check_recording(work, upload, FakeTools(heard="The early bus leaves at seven."))

    assert result(work)["problems"] == ["word error rate 68%", "ending missing"]


def test_reports_a_recording_that_wont_convert(work: Path, tmp_path: Path) -> None:
    upload = tmp_path / "abc.mp3"
    upload.write_bytes(b"ID3 not really")

    check_recording(work, upload, FakeTools())

    assert result(work)["errors"] == ["couldn't convert upload.mp3: Couldn't open input file"]
    assert not (work / "recording.wav").exists()


def test_warns_about_a_north_american_accent(work: Path, tmp_path: Path) -> None:
    upload = tmp_path / "abc.wav"
    write_wav(upload, 8.0)

    check_recording(work, upload, FakeTools(accent="us 80%, canada 10%"))

    assert result(work)["warnings"][0] == "the clip sounds North American (us 80%, canada 10%)"
