import argparse
import time
from pathlib import Path

import mlx.core as mx
import numpy as np
import soundfile as sf
from mlx_audio.tts.utils import load_model

from characters import CHARACTERS, OUT, reference_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("characters", nargs="*", default=list(CHARACTERS))
    parser.add_argument("--model", default="mlx-community/Qwen3-TTS-12Hz-1.7B-Base-bf16")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--stream", action="store_true")
    args = parser.parse_args()

    out = args.out or OUT / ("mlx-" + args.model.removeprefix("mlx-community/Qwen3-TTS-12Hz-").lower())
    out.mkdir(parents=True, exist_ok=True)
    mx.random.seed(1234)

    started = time.perf_counter()
    model = load_model(args.model)
    print(f"loaded {args.model} in {time.perf_counter() - started:.1f}s")

    for name in args.characters:
        character = CHARACTERS[name]
        for i, line in enumerate(character["lines"], 1):
            started = time.perf_counter()
            first_audio = None
            chunks = []
            for result in model.generate(
                text=line,
                lang_code="english",
                ref_audio=str(reference_path(name)),
                ref_text=character["reference"],
                stream=args.stream,
                streaming_interval=0.5,
            ):
                first_audio = first_audio or time.perf_counter() - started
                chunks.append(np.array(result.audio))
            elapsed = time.perf_counter() - started

            audio = np.concatenate(chunks)
            seconds = len(audio) / model.sample_rate
            sf.write(out / f"{name}_line{i}.wav", audio, model.sample_rate)
            print(
                f"  {name}_line{i}.wav: {seconds:.1f}s audio in {elapsed:.1f}s "
                f"({seconds / elapsed:.2f}x realtime, first audio after {first_audio:.2f}s)"
            )


if __name__ == "__main__":
    main()
