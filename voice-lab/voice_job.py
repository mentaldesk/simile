import argparse
import gc
import json
import os
import shutil
import subprocess
import zlib
from pathlib import Path

HERE = Path(__file__).parent
TORCH_PYTHON = HERE / ".venv" / "bin" / "python"
MLX_PYTHON = HERE / ".venv-mlx" / "bin" / "python"
RECORDING = "recording"
LONGEST = 60.0


def progress(fraction: float, message: str) -> None:
    print("JOB " + json.dumps({"progress": fraction, "message": message}), flush=True)


def read_params(work: Path) -> dict:
    return json.loads((work / "params.json").read_text(encoding="utf-8"))


def write_result(work: Path, result: dict) -> None:
    (work / "result.json").write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def candidate_seed(seed: int, n: int) -> int:
    return zlib.crc32(f"{seed}/{n}".encode())


def design(work: Path) -> None:
    os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")
    import soundfile as sf
    import torch

    import accent
    from design_npcs import MODEL, check
    from design_then_clone import load

    params = read_params(work)
    line, description, count = params["reference_line"], params["description"], params["count"]
    progress(0.0, "Loading the voice designer")
    designer = load(MODEL)
    wavs = []
    for n in range(1, count + 1):
        progress(0.05 + 0.5 * (n - 1) / count, f"Designing voice {n} of {count}")
        torch.manual_seed(candidate_seed(params["seed"], n))
        audio, sr = designer.generate_voice_design(text=line, language="English", instruct=description)
        wavs.append(work / f"candidate_{n}.wav")
        sf.write(wavs[-1], audio[0], sr)
    del designer
    gc.collect()
    torch.mps.empty_cache()

    subprocess.run([MLX_PYTHON, __file__, "listen", work, *wavs], check=True)
    heard = json.loads((work / "heard.json").read_text(encoding="utf-8"))

    progress(0.9, "Checking the accents")
    accent_model = accent.load()
    target = accent.expected(description)
    candidates = []
    for wav in wavs:
        audio, sr = sf.read(wav)
        accents = accent.classify(accent_model, audio, sr)
        checked = check(audio, sr, line, heard[wav.name], accents, target)
        clone_accents = accent.classify(accent_model, *sf.read(wav.with_name(f"{wav.stem}_1.wav")))
        lost = accent.problem(clone_accents, target)
        candidates.append(
            {
                "seconds": round(checked.seconds, 2),
                "heard": checked.heard,
                "word_error_rate": round(checked.word_error_rate, 3),
                "accent": accent.describe(accents),
                "clone_accent": accent.describe(clone_accents),
                "problems": checked.problems,
                "warnings": [f"cloned, it {lost}"] if lost else [],
            }
        )
    write_result(work, {"candidates": candidates})
    progress(1.0, "Designed")


def listen(work: Path, wavs: list[Path]) -> None:
    import transcribe as stt
    from mlx_audio.tts.utils import load_model

    from clone_accent_test import clone
    from speak_npcs import MODEL

    line = read_params(work)["reference_line"]
    progress(0.55, "Listening to each voice")
    whisper = stt.load()
    heard = {wav.name: stt.transcribe(whisper, str(wav)) for wav in wavs}
    del whisper
    tts = load_model(MODEL)
    for n, wav in enumerate(wavs, 1):
        progress(0.6 + 0.3 * (n - 1) / len(wavs), f"Cloning voice {n} of {len(wavs)}")
        clone(tts, wav, line, work, lines=[line])
    (work / "heard.json").write_text(json.dumps(heard, ensure_ascii=False), encoding="utf-8")


def check_recording(work: Path, upload: Path, tools=None) -> None:
    from import_voices import Clip, Models, check

    source = work / f"upload{upload.suffix.lower()}"
    shutil.move(upload, source)
    line = " ".join(read_params(work)["reference_line"].split())
    clip = Clip(RECORDING, source, line, digest="", reference_line_changes=False)
    progress(0.05, "Checking the recording")
    check([clip], tools or Models(TORCH_PYTHON), work, longest=LONGEST)
    write_result(
        work,
        {
            "seconds": clip.seconds,
            "heard": clip.heard,
            "word_error_rate": clip.word_error_rate,
            "accent": clip.accent,
            "sample_accents": clip.sample_accents,
            "errors": clip.errors,
            "problems": clip.problems,
            "warnings": clip.warnings,
        },
    )
    progress(1.0, "Checked")


def main() -> None:
    parser = argparse.ArgumentParser(description="One character's voice, for the server's voice jobs.")
    commands = parser.add_subparsers(dest="command", required=True)
    designing = commands.add_parser("design", help="design voices from work/params.json; runs in .venv")
    designing.add_argument("work", type=Path)
    listening = commands.add_parser("listen", help="transcribe and clone each candidate; runs in .venv-mlx")
    listening.add_argument("work", type=Path)
    listening.add_argument("wavs", nargs="+", type=Path)
    checking = commands.add_parser("check", help="check a recording of the reference line; runs in .venv-mlx")
    checking.add_argument("work", type=Path)
    checking.add_argument("upload", type=Path)
    args = parser.parse_args()

    if args.command == "design":
        design(args.work)
    elif args.command == "listen":
        listen(args.work, args.wavs)
    else:
        check_recording(args.work, args.upload)


if __name__ == "__main__":
    main()
