# voice-lab

Prototype of the NPC voice pipeline described under [Voices](../README.md#voices).

- `characters.py`: the test characters. Each has a voice description or a recorded clip, a reference line, and lines to speak.
- `design_then_clone.py`: PyTorch (`qwen-tts`). Designs a voice for any character without a clip in `voices/`, then speaks their lines in it.
- `clone_mlx.py`: the same cloning step on MLX, about 3.5x faster on Apple Silicon. `--stream` measures time to first audio.

## Setup

The two scripts need separate virtualenvs: `qwen-tts` pins `transformers` 4.57.3, and `mlx-audio` pulls in 5.x.

```bash
python3.12 -m venv .venv && .venv/bin/pip install -r requirements-torch.txt
python3.12 -m venv .venv-mlx && .venv-mlx/bin/pip install -r requirements-mlx.txt
```

Models download from Hugging Face on first use (about 4 GB each for the 1.7B models).

## Running

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python design_then_clone.py [character ...] [--clone-model Qwen/Qwen3-TTS-12Hz-0.6B-Base] [--out DIR]
.venv-mlx/bin/python clone_mlx.py [character ...] [--model mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit] [--stream] [--out DIR]
```

Generated lines go to `out/`.
