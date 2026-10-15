# Voices

Each NPC's voice. `<id>.wav` is the reference clip (24 kHz mono) of them saying their
`voice.reference_line`, and `<id>.txt` is its transcript. The server clones it for everything they
say. `samples/` has three more lines in each voice, to judge by ear.

Made by `voice-lab/design_npcs.py` and `voice-lab/speak_npcs.py`, which fill in only what's
missing. See [`voice-lab/README.md`](../../voice-lab/README.md#the-villages-voices).
