import argparse
import json
import shutil
import subprocess
import zlib
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

from design_then_clone import load
from npcs import VOICES, clip_path, has_voice, load_npcs, remove_voice, set_reference_clip, word_error_rate, words

HERE = Path(__file__).parent
OUT = HERE / "out" / "design"
MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
SAMPLE_RATE = 24_000
ATTEMPTS = 3
MIN_SECONDS, MAX_SECONDS = 5.0, 10.0
MIN_RMS_DB, MAX_RMS_DB = -30.0, -14.0
CLIPPED = 0.99
MAX_WORD_ERROR_RATE = 0.1


@dataclass
class Check:
    seconds: float
    peak_db: float
    rms_db: float
    heard: str
    word_error_rate: float
    problems: list[str] = field(default_factory=list)


def decibels(amplitude: float) -> float:
    return 20 * np.log10(max(amplitude, 1e-9))


def check(wav: np.ndarray, sr: int, line: str, heard: str) -> Check:
    result = Check(
        seconds=len(wav) / sr,
        peak_db=decibels(np.abs(wav).max()),
        rms_db=decibels(np.sqrt(np.mean(wav**2))),
        heard=heard,
        word_error_rate=word_error_rate(line, heard),
    )
    if sr != SAMPLE_RATE or wav.ndim != 1:
        result.problems.append(f"{wav.ndim}-channel {sr} Hz, not mono {SAMPLE_RATE} Hz")
    if not MIN_SECONDS <= result.seconds <= MAX_SECONDS:
        result.problems.append(f"{result.seconds:.1f}s long")
    if not MIN_RMS_DB <= result.rms_db <= MAX_RMS_DB:
        result.problems.append(f"RMS {result.rms_db:.1f} dBFS")
    if clipped := int(np.sum(np.abs(wav) >= CLIPPED)):
        result.problems.append(f"{clipped} clipped samples")
    if result.word_error_rate > MAX_WORD_ERROR_RATE:
        result.problems.append(f"word error rate {result.word_error_rate:.0%}")
    if words(heard)[-2:] != words(line)[-2:]:
        result.problems.append("ending missing")
    return result


def transcribe(mlx_python: Path, clip: Path) -> str:
    run = subprocess.run([mlx_python, HERE / "transcribe.py", clip], capture_output=True, text=True, check=True)
    return json.loads(run.stdout.splitlines()[-1])[str(clip)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Design a voice for each NPC in content/npcs without one.")
    parser.add_argument("npcs", nargs="*", help="NPC ids (default: all)")
    parser.add_argument("--force", action="store_true", help="redesign voices that already exist")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--mlx-python", type=Path, default=HERE / ".venv-mlx" / "bin" / "python")
    args = parser.parse_args()

    npcs = load_npcs(args.npcs)
    if not args.npcs:
        for clip in VOICES.glob("*.wav"):
            if clip.stem not in npcs:
                remove_voice(clip.stem)
                print(f"Removed the voice of {clip.stem}, who is no longer an NPC")
    todo = {npc_id: npc for npc_id, npc in npcs.items() if args.force or not has_voice(npc_id, npc)}
    if not todo:
        print("Every NPC has a voice. Use --force to redesign them.")
        return

    VOICES.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    designer = load(MODEL)
    report = []
    for npc_id, npc in todo.items():
        voice = npc["voice"]
        attempts = []
        for attempt in range(1, ATTEMPTS + 1):
            seed = zlib.crc32(f"{args.seed}/{npc_id}/{attempt}".encode())
            torch.manual_seed(seed)
            wavs, sr = designer.generate_voice_design(
                text=voice["reference_line"], language="English", instruct=voice["description"]
            )
            candidate = OUT / f"{npc_id}_{attempt}.wav"
            sf.write(candidate, wavs[0], sr)
            result = check(wavs[0], sr, voice["reference_line"], transcribe(args.mlx_python, candidate))
            attempts.append((result, attempt, seed, candidate))
            print(f"{npc_id} attempt {attempt} (seed {seed}): {', '.join(result.problems) or 'ok'}")
            print(f"  heard: {result.heard}")
            if not result.problems:
                break

        result, attempt, seed, candidate = min(attempts, key=lambda a: (len(a[0].problems), a[0].word_error_rate))
        remove_voice(npc_id)
        clip = clip_path(npc_id)
        shutil.copyfile(candidate, clip)
        clip.with_suffix(".txt").write_text(voice["reference_line"] + "\n", encoding="utf-8")
        set_reference_clip(npc_id, clip)
        report.append(
            f"| `{npc_id}` | {attempt} of {len(attempts)} | {seed} | {result.seconds:.1f} s | "
            f"{result.peak_db:.1f} | {result.rms_db:.1f} | {result.word_error_rate:.0%} | "
            f"{', '.join(result.problems) or 'pass'} |"
        )

    print("\n| NPC | Kept attempt | Seed | Length | Peak dBFS | RMS dBFS | Word error rate | Checks |")
    print("|---|---|--:|--:|--:|--:|--:|---|")
    print("\n".join(report))


if __name__ == "__main__":
    main()
