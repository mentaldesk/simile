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

import accent
from design_then_clone import load
from npcs import (
    VOICES,
    clip_path,
    imported_voices,
    load_npcs,
    misheard,
    remove_voice,
    save_imported,
    set_reference_clip,
    to_design,
    word_error_rate,
)

HERE = Path(__file__).parent
OUT = HERE / "out" / "design"
SEEDS = VOICES / "seeds.json"
MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign"
SAMPLE_RATE = 24_000
ATTEMPTS = 6
MIN_SECONDS, MAX_SECONDS = 5.0, 10.0
MIN_RMS_DB, MAX_RMS_DB = -30.0, -14.0
CLIPPED = 0.99


@dataclass
class Check:
    seconds: float
    peak_db: float
    rms_db: float
    heard: str
    word_error_rate: float
    accents: list[tuple[str, float]]
    accent_miss: float
    problems: list[str] = field(default_factory=list)


def decibels(amplitude: float) -> float:
    return 20 * np.log10(max(amplitude, 1e-9))


def check(
    wav: np.ndarray, sr: int, line: str, heard: str, accents: list[tuple[str, float]], target: str | None
) -> Check:
    result = Check(
        seconds=len(wav) / sr,
        peak_db=decibels(np.abs(wav).max()),
        rms_db=decibels(np.sqrt(np.mean(wav**2))),
        heard=heard,
        word_error_rate=word_error_rate(line, heard),
        accents=accents,
        accent_miss=accent.miss(accents, target),
    )
    if sr != SAMPLE_RATE or wav.ndim != 1:
        result.problems.append(f"{wav.ndim}-channel {sr} Hz, not mono {SAMPLE_RATE} Hz")
    if not MIN_SECONDS <= result.seconds <= MAX_SECONDS:
        result.problems.append(f"{result.seconds:.1f}s long")
    if not MIN_RMS_DB <= result.rms_db <= MAX_RMS_DB:
        result.problems.append(f"RMS {result.rms_db:.1f} dBFS")
    if clipped := int(np.sum(np.abs(wav) >= CLIPPED)):
        result.problems.append(f"{clipped} clipped samples")
    result.problems += misheard(line, heard)
    if problem := accent.problem(accents, target):
        result.problems.append(problem)
    return result


def save_seeds(seeds: dict[str, int]) -> None:
    SEEDS.write_text(json.dumps(dict(sorted(seeds.items())), indent=2) + "\n", encoding="utf-8")


def transcribe(mlx_python: Path, clip: Path) -> str:
    run = subprocess.run([mlx_python, HERE / "transcribe.py", clip], capture_output=True, text=True, check=True)
    return json.loads(run.stdout.splitlines()[-1])[str(clip)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Design a voice for each NPC in content/npcs without one.")
    parser.add_argument("npcs", nargs="*", help="NPC ids (default: all)")
    parser.add_argument("--force", action="store_true", help="redesign voices that already exist")
    parser.add_argument("--seed", type=int, help=f"default: the NPC's seed in {SEEDS.name}, or 0")
    parser.add_argument("--mlx-python", type=Path, default=HERE / ".venv-mlx" / "bin" / "python")
    args = parser.parse_args()

    npcs = load_npcs(args.npcs)
    seeds = json.loads(SEEDS.read_text()) if SEEDS.exists() else {}
    if not args.npcs:
        for clip in VOICES.glob("*.wav"):
            if clip.stem not in npcs:
                remove_voice(clip.stem)
                print(f"Removed the voice of {clip.stem}, who is no longer an NPC")
        if set(seeds) - set(npcs):
            seeds = {npc_id: seed for npc_id, seed in seeds.items() if npc_id in npcs}
            save_seeds(seeds)
        imported = imported_voices()
        if set(imported) - set(npcs):
            save_imported({npc_id: digest for npc_id, digest in imported.items() if npc_id in npcs})
    if kept := sorted(set(npcs) & set(imported_voices())):
        print(f"Keeping the imported voices of {', '.join(kept)}. Remove them from imported.json to redesign them.")
    todo = to_design(npcs, args.force)
    if not todo:
        print("Nothing to design." if args.force else "Every NPC has a voice. Use --force to redesign them.")
        return

    VOICES.mkdir(parents=True, exist_ok=True)
    OUT.mkdir(parents=True, exist_ok=True)
    designer = load(MODEL)
    accent_model = accent.load()
    report = []
    for npc_id, npc in todo.items():
        voice = npc["voice"]
        target = accent.expected(voice["description"])
        seeds[npc_id] = args.seed if args.seed is not None else seeds.get(npc_id, 0)
        attempts = []
        for attempt in range(1, ATTEMPTS + 1):
            seed = zlib.crc32(f"{seeds[npc_id]}/{npc_id}/{attempt}".encode())
            torch.manual_seed(seed)
            wavs, sr = designer.generate_voice_design(
                text=voice["reference_line"], language="English", instruct=voice["description"]
            )
            candidate = OUT / f"{npc_id}_{attempt}.wav"
            sf.write(candidate, wavs[0], sr)
            heard = transcribe(args.mlx_python, candidate)
            accents = accent.classify(accent_model, wavs[0], sr)
            result = check(wavs[0], sr, voice["reference_line"], heard, accents, target)
            attempts.append((result, attempt, seed, candidate))
            print(f"{npc_id} attempt {attempt} (seed {seed}): {', '.join(result.problems) or 'ok'}")
            print(f"  heard: {result.heard}")
            print(f"  accent: {accent.describe(accents)}")
            if not result.problems:
                break

        result, attempt, seed, candidate = min(
            attempts, key=lambda a: (len(a[0].problems), a[0].accent_miss, a[0].word_error_rate)
        )
        remove_voice(npc_id)
        clip = clip_path(npc_id)
        shutil.copyfile(candidate, clip)
        clip.with_suffix(".txt").write_text(voice["reference_line"] + "\n", encoding="utf-8")
        set_reference_clip(npc_id, clip)
        save_seeds(seeds)
        report.append(
            f"| `{npc_id}` | {attempt} of {len(attempts)} | {seed} | {result.seconds:.1f} s | "
            f"{result.peak_db:.1f} | {result.rms_db:.1f} | {result.word_error_rate:.0%} | "
            f"{accent.describe(result.accents)} | "
            f"{', '.join(result.problems) or 'pass'} |"
        )

    print("\n| NPC | Kept attempt | Seed | Length | Peak dBFS | RMS dBFS | Word error rate | Accent | Checks |")
    print("|---|---|--:|--:|--:|--:|--:|---|---|")
    print("\n".join(report))


if __name__ == "__main__":
    main()
