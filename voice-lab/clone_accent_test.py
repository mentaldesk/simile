import argparse
import json
import subprocess
import zlib
from pathlib import Path

import mlx.core as mx
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model
from mlx_audio.utils import load_audio

from npcs import SAMPLE_LINES
from speak_npcs import MODEL, TOKENS_PER_SECOND

HERE = Path(__file__).parent
OUT = HERE / "out" / "clone-accent"


def clone(
    model, clip: Path, transcript: str | None, out: Path, seeds: int = 1, lines: list[str] = SAMPLE_LINES, **settings
) -> list[Path]:
    """Speak the lines in the clip's voice the way speak_npcs.py does. No transcript clones from the voice alone."""
    reference = load_audio(str(clip), sample_rate=model.sample_rate)
    out.mkdir(parents=True, exist_ok=True)
    paths = []
    for seed in range(seeds):
        for n, line in enumerate(lines, 1):
            stem = f"{clip.stem}_{n}"
            mx.random.seed(zlib.crc32(f"{seed}/{stem}".encode()))
            results = model.generate(
                text=line,
                ref_audio=reference,
                ref_text=transcript,
                max_tokens=int(TOKENS_PER_SECOND * (3 + len(line) / 5)),
                **{"lang_code": "english"} | settings,
            )
            path = out / (f"{stem}.wav" if seed == 0 else f"{stem}_seed{seed}.wav")
            sf.write(path, np.concatenate([np.array(result.audio) for result in results]), model.sample_rate)
            paths.append(path)
    return paths


def accents(wavs: list[Path], torch_python: Path) -> dict[str, str]:
    run = [torch_python, HERE / "accent.py", *map(str, wavs)]
    return json.loads(subprocess.run(run, capture_output=True, text=True, check=True).stdout.splitlines()[-1])


def main() -> None:
    parser = argparse.ArgumentParser(description="Check whether the clone model keeps a reference clip's accent.")
    parser.add_argument("clips", nargs="+", type=Path, help="WAVs, each with its transcript in a .txt beside it")
    parser.add_argument("--model", default=MODEL)
    parser.add_argument("--seeds", type=int, default=1, help="how many times to speak each sample line")
    parser.add_argument("--no-transcript", action="store_true", help="clone from the voice alone, without ref_text")
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--torch-python", type=Path, default=HERE / ".venv" / "bin" / "python")
    args = parser.parse_args()

    model = load_model(args.model)
    samples = {}
    for clip in args.clips:
        transcript = None if args.no_transcript else clip.with_suffix(".txt").read_text(encoding="utf-8").strip()
        samples[clip] = clone(model, clip, transcript, args.out, args.seeds)
    heard = accents([*args.clips, *(path for paths in samples.values() for path in paths)], args.torch_python)

    print("\n| Reference | Heard as | Samples heard as | Samples that kept it |")
    print("|---|---|---|--:|")
    for clip, paths in samples.items():
        reference = heard[str(clip)]
        kept = sum(heard[str(path)].split()[0] == reference.split()[0] for path in paths)
        print(f"| `{clip.name}` | {reference} | {' · '.join(heard[str(p)] for p in paths)} | {kept} of {len(paths)} |")


if __name__ == "__main__":
    main()
