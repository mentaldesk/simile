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

Models download from Hugging Face on first use (about 4 GB each for the 1.7B models, 80 MB for the accent classifier).

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

- `design_npcs.py` designs a voice for each NPC whose `voice.reference_clip` isn't `content/voices/<id>.wav` yet: the VoiceDesign model says the NPC's reference line in the voice their description asks for. It saves the clip (24 kHz mono WAV) with its transcript (`<id>.txt`) and sets `reference_clip`. With no NPCs named, it also deletes the voices of NPCs that no longer exist. It doesn't replace an [imported voice](#importing-a-recorded-voice).
- Each clip must be 5–10 s long, at -30 to -14 dBFS RMS and unclipped, and Whisper (`transcribe.py`, in `.venv-mlx`) must hear the reference line with at most a 10% word error rate, last two words included. The accent classifier (`accent.py`, in `.venv`) must hear the accent the description names, or if it doesn't know that accent, must not hear a North American one. A clip that fails is redesigned with another seed, at most five times, and the attempt with the fewest problems, then the closest accent, is kept. The table at the end says which checks the kept clips failed. Every attempt stays in `out/design/`.
- `speak_npcs.py` speaks `SAMPLE_LINES` from `npcs.py` in each voice with the server's clone model, to `content/voices/samples/<id>_<n>.m4a`, to check that a voice holds up away from its reference line. Every NPC says the same lines, so voices are easy to compare. Its table shows the accent the classifier hears in each, since cloning can lose it. Redesigning a voice deletes its samples, so the next run speaks them again.
- After designing, `design_npcs.py` measures how fast each new voice speaks, which paces their lines, with `simile voice measure` in `server/` ([speaking rates](../server/simile/voice/README.md#speaking-rates)). That needs the server's voice extra (`cd server && uv sync --extra voice`).
- Seeds come from the NPC's base seed, the NPC and the attempt. The base seed is `--seed`, or else the one saved in `content/voices/seeds.json` by the last design, so a rerun with `--force` gives the same voices.

### Accents

VoiceDesign leans hard towards an American accent. It ignores a "faint lilt" entirely, and even "A heavy Irish accent." comes out American on most seeds. Name the accent plainly at the start of the description, and try several seeds and wordings. The clone model keeps a strong accent, such as macOS's Australian, Indian and Irish voices, but pulls a faint one back towards American, so check the samples as well as the reference clip. It needs the clip's transcript to do it: from the voice alone (`--no-transcript`), Karen's Australian accent came out American.

To check a recording before it becomes a voice, such as a speaker with the accent an NPC needs, run `clone_accent_test.py`. It speaks `SAMPLE_LINES` in each clip's voice the way `speak_npcs.py` does, and prints the accent the classifier hears in the clip and in each sample. Each clip needs its transcript in a `.txt` beside it. Samples go to `out/clone-accent/`.

```bash
.venv-mlx/bin/python clone_accent_test.py clip.wav [clip.wav ...] [--seeds N] [--model ID] [--no-transcript] [--out DIR]
```

The classifier is [CommonAccent ECAPA](https://huggingface.co/Jzuluaga/accent-id-commonaccent_ecapa) (speechbrain), which knows 16 accents of English: England, US, Canada, Australia, New Zealand, India, Scotland, Ireland, Wales, Africa, Malaysia, Singapore, the Philippines, Hong Kong, Bermuda and the South Atlantic. `accent.KNOWN` maps the words a description uses to those. For any other accent, such as Danish, French or Portuguese, it can only say whether a clip sounds North American, so listen. It labelled macOS's Irish voice (Moira) `england` on one line and `ireland` on another, so an Irish clip may score as English.

### Importing a recorded voice

Since VoiceDesign can't do a strong accent, a resident's voice can come from a recording instead. `import_voices.py` checks each clip in a folder and makes it the resident's voice. It runs in `.venv-mlx` and needs `.venv` too.

```bash
.venv-mlx/bin/python import_voices.py --scripts [--only id,...]
.venv-mlx/bin/python import_voices.py [folder] [--dry-run] [--force] [--only id,...]
```

- The folder (`incoming/` by default, ignored by git) holds one clip per resident, named after them (`<id>.wav`, `.mp3` or `.m4a`), with `<id>.txt` holding exactly what the clip says. Write the script from the resident's reference line and it doubles as the transcript: `--scripts` writes each reference line to `<id>.txt`, keeping any that already exist.
- Residents without a clip are left alone. Unknown names, clips without a transcript and two clips for one resident are reported and skipped, never guessed.
- Each clip is converted to 24 kHz mono 16-bit WAV with `afconvert`, then checked:
  - It must be 5–25 s long. N2c found a long reference keeps an accent as well as a short one.
  - Whisper must hear the transcript with at most a 10% word error rate, last two words included. The clone model needs the right transcript to keep the accent.
  - The transcript becomes the resident's `reference_line`, so it must be 12–25 words without a `!`, which `make test` checks.
  - The accent classifier listens to the clip and to `SAMPLE_LINES` cloned from it, the way `clone_accent_test.py` does. This only warns: anything it hears as North American is flagged, and the rest is up to your ear.
- A clip that passes becomes the resident's voice: `content/voices/<id>.wav` and `<id>.txt`, `voice.reference_clip` and `voice.reference_line` in `content/npcs/<id>.json`, and new samples from `speak_npcs.py`. The check clones with the same seeds as `speak_npcs.py`, so its samples sound just like the new ones.
- Then it measures how fast each new voice speaks, as `design_npcs.py` does.
- `--dry-run` runs every check and changes nothing. The converted clips and their cloned samples are in `out/import/` to listen to.
- `--force` imports a clip that fails the length or Whisper check, but never a transcript that can't be a reference line. It also reimports a clip that was already imported unchanged, which is otherwise skipped.
- `content/voices/imported.json` lists the imported voices. `design_npcs.py` doesn't redesign them, even with `--force`, as long as the resident still has that voice. If they lose it, for example when `simile generate-npcs` clears `reference_clip`, it designs a new one. Remove a resident from the list to redesign their voice.
- Restart the server to hear a new voice. The saved village doesn't keep voices, so there's no need for `simile reset`.

## Tests

`tests/` covers `import_voices.py` and the `npcs.py` helpers it shares with `design_npcs.py`, with fakes instead of models. `make test` doesn't run them. CI runs them (`.github/workflows/voice-lab.yml`) on changes to `voice-lab/` or `content/npcs/`:

```bash
uvx --python 3.12 pytest
```
