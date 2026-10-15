import argparse
import subprocess
import tempfile
import zlib
from pathlib import Path

import mlx.core as mx
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model
from mlx_audio.utils import load_audio

import transcribe
from npcs import SAMPLE_LINES, SAMPLES, clip_path, has_voice, load_npcs, sample_paths, word_error_rate

MODEL = "mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit"
TOKENS_PER_SECOND = 12.5


def main() -> None:
    parser = argparse.ArgumentParser(description="Speak sample lines in each NPC's designed voice.")
    parser.add_argument("npcs", nargs="*", help="NPC ids (default: all)")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--force", action="store_true", help="respeak samples that already exist")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    todo = {}
    for npc_id, npc in load_npcs(args.npcs).items():
        if not has_voice(npc_id, npc):
            print(f"{npc_id} has no voice yet: run design_npcs.py first")
            continue
        lines = zip(SAMPLE_LINES, sample_paths(npc_id), strict=True)
        if lines := [(line, path) for line, path in lines if args.force or not path.exists()]:
            todo[npc_id] = (npc, lines)
    if not todo:
        print("Every NPC's samples exist. Use --force to respeak them.")
        return

    SAMPLES.mkdir(parents=True, exist_ok=True)
    model = load_model(args.model)
    whisper = transcribe.load()
    report = []
    with tempfile.TemporaryDirectory() as tmp:
        for npc_id, (npc, lines) in todo.items():
            reference = load_audio(str(clip_path(npc_id)), sample_rate=model.sample_rate)
            for line, path in lines:
                mx.random.seed(zlib.crc32(f"{args.seed}/{path.stem}".encode()))
                results = model.generate(
                    text=line,
                    lang_code="english",
                    ref_audio=reference,
                    ref_text=npc["voice"]["reference_line"],
                    max_tokens=int(TOKENS_PER_SECOND * (3 + len(line) / 5)),
                )
                audio = np.concatenate([np.array(result.audio) for result in results])
                wav = Path(tmp) / f"{path.stem}.wav"
                sf.write(wav, audio, model.sample_rate)
                heard = transcribe.transcribe(whisper, str(wav))
                subprocess.run(["afconvert", "-f", "m4af", "-d", "aac", "-b", "48000", wav, path], check=True)
                seconds, error_rate = len(audio) / model.sample_rate, word_error_rate(line, heard)
                print(f"{path.name}: {seconds:.1f} s, word error rate {error_rate:.0%}")
                print(f"  heard: {heard}")
                report.append(f"| `{path.name}` | {seconds:.1f} s | {error_rate:.0%} | {heard} |")

    print("\n| Sample | Length | Word error rate | Heard |")
    print("|---|--:|--:|---|")
    print("\n".join(report))


if __name__ == "__main__":
    main()
