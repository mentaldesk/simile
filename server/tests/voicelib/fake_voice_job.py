"""Stands in for `voice-lab/voice_job.py`, without its models."""

import json
import shutil
import sys
import time
import wave
from pathlib import Path

VOICE_LAB = Path(__file__).resolve().parents[3] / "voice-lab"


def report(progress: float, message: str) -> None:
    print("JOB " + json.dumps({"progress": progress, "message": message}), flush=True)


def write_wav(path: Path, seconds: float, sample: int = 1) -> None:
    with wave.open(str(path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(24000)
        audio.writeframes(sample.to_bytes(2, "little") * int(seconds * 24000))


def design(work: Path) -> None:
    params = json.loads((work / "params.json").read_text())
    candidates = []
    for n in range(1, params["count"] + 1):
        report(n / (params["count"] + 1), f"Designing voice {n}")
        write_wav(work / f"candidate_{n}.wav", 7.0, sample=n)
        write_wav(work / f"candidate_{n}_1.wav", 7.0, sample=100 + n)
        candidates.append(
            {
                "seconds": 7.0,
                "heard": params["reference_line"],
                "word_error_rate": 0.0,
                "accent": "scotland 90%",
                "clone_accent": "england 60%, scotland 30%",
                "problems": [] if n > 1 else ["7.0s long"],
                "warnings": [],
            }
        )
    (work / "result.json").write_text(json.dumps({"candidates": candidates}))


def check(work: Path, upload: Path, heard: str, hold: str) -> None:
    while hold and not Path(hold).exists():
        time.sleep(0.01)
    sys.path.insert(0, str(VOICE_LAB))
    from import_voices import ConversionError
    from voice_job import check_recording

    class Tools:
        def convert(self, source: Path, wav: Path) -> None:
            if source.read_bytes()[:4] != b"RIFF":
                raise ConversionError("Couldn't open input file")
            shutil.copyfile(source, wav)

        def transcribe(self, wav: Path) -> str:
            return heard

        def clone(self, wav: Path, transcript: str, out: Path) -> list[Path]:
            out.mkdir(parents=True, exist_ok=True)
            paths = [out / f"{wav.stem}_{n}.wav" for n in (1, 2, 3)]
            for path in paths:
                write_wav(path, 3.0)
            return paths

        def accents(self, wavs: list[Path]) -> dict[str, str]:
            return {str(wav): "scotland 90%" for wav in wavs}

    check_recording(work, upload, Tools())


if __name__ == "__main__":
    if sys.argv[1] == "design":
        design(Path(sys.argv[2]))
    else:
        check(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4], sys.argv[5])
