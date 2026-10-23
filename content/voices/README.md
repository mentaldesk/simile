# Voices

Each NPC's voice. `<id>.wav` is the reference clip (24 kHz mono) of them saying their
`voice.reference_line`, and `<id>.txt` is its transcript. The server clones it for everything they
say. `samples/` has three more lines in each voice, to judge by ear.

Made by `voice-lab/design_npcs.py` and `voice-lab/speak_npcs.py`, which fill in only what's
missing. `seeds.json` holds the seed each voice was designed from, so a rerun gives the same voice.
See [`voice-lab/README.md`](../../voice-lab/README.md#the-villages-voices).

A voice can also be a recording, imported by `voice-lab/import_voices.py`
([how](../../voice-lab/README.md#importing-a-recorded-voice)). `imported.json` lists those, and
`design_npcs.py` leaves them alone.

`rates.json` is how fast each voice speaks, which paces their lines. `simile voice measure` writes
it, and `design_npcs.py` and `import_voices.py` run that for each voice they make
([how](../../server/simile/voice/README.md#speaking-rates)).

Each resident's accent was set by hand (N2b, #70) in their `backstory`, `speaking_style` and
`voice.description`. Rerunning `simile generate-npcs` replaces those along with everything else.

`greetings/` has three or four short greetings for each resident, which the client plays when they
start talking to the player. `greetings/lines.json` is what they say, and `uv run simile greetings`
records them ([how](../../server/simile/voicing/README.md#greetings)), with ElevenLabs when there's
a key. `elevenlabs.json` is each resident's voice from the ElevenLabs library, which has their accent,
and the audio tags said before each greeting. Those voices are only for prerecorded clips: everything
else a resident says is cloned from their clip here.
