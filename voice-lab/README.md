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

## The village's voices

`design_npcs.py` and `speak_npcs.py` give the NPCs in `content/npcs/` their voices, once, after the NPCs are generated. Both need both virtualenvs.

```bash
PYTORCH_ENABLE_MPS_FALLBACK=1 .venv/bin/python design_npcs.py [npc ...] [--force] [--seed N]
.venv-mlx/bin/python speak_npcs.py [npc ...] [--force] [--seed N]
```

- `design_npcs.py` designs a voice for each NPC whose `voice.reference_clip` isn't `content/voices/<id>.wav` yet: the VoiceDesign model says the NPC's reference line in the voice their description asks for. It saves the clip (24 kHz mono WAV) with its transcript (`<id>.txt`) and sets `reference_clip`. With no NPCs named, it also deletes the voices of NPCs that no longer exist.
- Each clip must be 5–10 s long, at -30 to -14 dBFS RMS and unclipped, and Whisper (`transcribe.py`, in `.venv-mlx`) must hear the reference line with at most a 10% word error rate, last two words included. A clip that fails is redesigned with another seed, at most twice, and the attempt with the fewest problems is kept. The table at the end says which checks the kept clips failed. Every attempt stays in `out/design/`.
- `speak_npcs.py` speaks `SAMPLE_LINES` from `npcs.py` in each voice with the server's clone model, to `content/voices/samples/<id>_<n>.m4a`, to check that a voice holds up away from its reference line. Every NPC says the same lines, so voices are easy to compare. Redesigning a voice deletes its samples, so the next run speaks them again.
- Seeds come from `--seed`, the NPC and the attempt, so a rerun with `--force` gives the same voices.
