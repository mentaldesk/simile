import argparse
import gc
import time
from pathlib import Path

import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

from characters import CHARACTERS, OUT, VOICES, reference_path

DEVICE = "mps"
DTYPE = torch.bfloat16


def load(model_id: str) -> Qwen3TTSModel:
    start = time.perf_counter()
    model = Qwen3TTSModel.from_pretrained(model_id, device_map=DEVICE, dtype=DTYPE, attn_implementation="sdpa")
    print(f"loaded {model_id} in {time.perf_counter() - start:.1f}s")
    return model


def save(path: Path, wav, sr: int, started: float) -> None:
    elapsed = time.perf_counter() - started
    seconds = len(wav) / sr
    sf.write(path, wav, sr)
    print(f"  {path.name}: {seconds:.1f}s audio in {elapsed:.1f}s ({seconds / elapsed:.2f}x realtime)")


def free(model: Qwen3TTSModel) -> None:
    del model
    gc.collect()
    torch.mps.empty_cache()



def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("characters", nargs="*", default=list(CHARACTERS))
    parser.add_argument("--clone-model", default="Qwen/Qwen3-TTS-12Hz-1.7B-Base")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    VOICES.mkdir(exist_ok=True)
    args.out.mkdir(parents=True, exist_ok=True)
    torch.manual_seed(1234)
    selected = {name: CHARACTERS[name] for name in args.characters}

    to_design = {name: c for name, c in selected.items() if not reference_path(name).exists()}
    if to_design:
        designer = load("Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign")
        for name, character in to_design.items():
            started = time.perf_counter()
            wavs, sr = designer.generate_voice_design(
                text=character["reference"], language="English", instruct=character["voice"]
            )
            save(reference_path(name), wavs[0], sr, started)
        free(designer)

    cloner = load(args.clone_model)
    for name, character in selected.items():
        prompt = cloner.create_voice_clone_prompt(ref_audio=str(reference_path(name)), ref_text=character["reference"])
        for i, line in enumerate(character["lines"], 1):
            started = time.perf_counter()
            wavs, sr = cloner.generate_voice_clone(text=line, language="English", voice_clone_prompt=prompt)
            save(args.out / f"{name}_line{i}.wav", wavs[0], sr, started)


if __name__ == "__main__":
    main()
