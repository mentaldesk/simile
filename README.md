# Running it

You need [uv](https://docs.astral.sh/uv/), [Node](https://nodejs.org) 22.12 or later, make, and
[Claude Code](https://claude.com/claude-code) installed and logged in. The NPCs think through that
login, so there's no API key.

```bash
./run.sh
```

It installs what the village needs, starts it and opens the title menu at http://localhost:5173
(http://localhost:5173/?play goes straight into the village). Ctrl-C stops it.

Voices are off: the residents talk in speech bubbles, and each one greets you out loud, in their own
voice, when they start talking to you. On a Mac with Apple Silicon, `SIMILE_VOICE=1 ./run.sh` turns
their voices on. The first voiced run downloads the voice model, about 3 GB, and the model needs
about 3 GB of memory. The greetings play either way, on any machine. Where voice-lab is set up,
picking a character's voice in the creator records their greetings with the same model in
voice-lab's virtualenv, which loads it, and the first time downloads it, even with voices off.

## Controls

| Keys | What they do |
|---|---|
| ← → (or A D) | Walk, or run once Shift is on. In the air, steer. |
| Shift | Switch between walking and running. You keep running, stopped or on stairs and ladders, until you press it again. |
| Space | Jump. Hold it to jump higher, and run to jump further. Walk off a ledge and you land safely on whatever is below. |
| ↑ (or W) | Upstairs or up a ladder, from the tile beside its foot. On the lift, up a floor. |
| ↓ (or S) | Downstairs or down a ladder, from the tile beside its top. On the lift, down a floor. |
| E | Read the news at a terminal, look at a mural or a painting, order at a counter, pick up what you left when you collapsed, or look at a clue in Aris's workshop. Otherwise go through a door, or talk to the ringed resident. |
| F | Eat, once you're peckish: a meal at home, at the café or the noodle bar, or food you carry. Hunger rises while you play, and if it runs out you collapse. |
| J | Open or close your journal: what you've learned about what happened to Aris, from whom and when, and the leads still open. A red mark shows where your infrared eye caught someone flush. |
| L | Switch your lamp on or off. Parts of the tunnels are dark, and only the lamp lights them. Its battery runs down while it's on: the gauge under the controls shows what's left, and standing at a plug charges it, at home, at the café or the noodle bar, or in the tunnels. |
| Enter | Talk to the ringed resident, then send what you typed. |
| Tab | Choose who to talk to. Clicking a resident does too. |
| Esc | Close the chat or a panel. |
| ? | Show or hide these controls in the game. |

A small tag over each door, flight of stairs, ladder and the lift names its keys. Where E is used for
something else, like a mural beside a door, ↑ takes the door.

# Concept

Simile is a simulation that takes the form of an isometric video game set in a small village: pixel art characters walking through pre-rendered 3D scenery. 

## NPCs (agents)

### Core values

The village has various NPC characters. Each NPC has certain core values that are more or less important to them. The list of things they might value are:
- Freedom
- Independence
- Self Respect
- Self Actualization
- Creativity
- Honesty
- Compassion
- Loyalty
- Justice
- Responsibility
- Security
- Equality
- Tradition
- Obedience
- Success
- Ambition
- Discipline   
- Knowledge   
- Open Mindedness   
- PeaceOfMind   
- Pleasure   
- Connection   
- Adventure
- Optimism

NPCs are generated and assigned scores (between 0 and 1) for each of those core values. Those core values will be used to determine each NPC's behaviour... for example, how likely they are to seek conversations with the player or other NPCs and, once in a conversation, how long they are likely to stay in the conversation (or conversely how quickly they might seek to end it). The values also determine the kinds of things the NPCs are likely to want to talk about and the sorts of other NPCs or players they will enjoy speaking with. If another player or NPC tends to speak about things the agents is interested in, they will be more engaged in the conversation and start to be more interested in that NPC/player.

NPCs can also speak about other NPCs they've met or other conversations they've had and indeed they should be more likely to do this if such conversations are:
1. either recent
2. and/or interesting to them

### Relationships

NPCs establish and develop relationships with other NPCs and with the player that they maintain over time. Each interraction with another entity can influence how they feel about that individual with respect to:
- Like/Dislike: do I enjoy this person?	This will me more likely if they have conversations about topics they care about (per their core values).
- Trust: Will they keep promises, keep secrets, not betray me?	
- Respect: Do I rate their competence, status or strength? (You can respect someone you dislike.)	
- Familiarity: How well I know them. Grows with any interaction and rarely decreases.	

NPCs will be more likey to seek out conversations with other NPCs that they consider friends (based on the score/tally that they keey for each of the other entities per the above 4 metrics (again, on a scale of 0 to 1 for each metric)... and they will avoid or only have short interractions with other NPCs or players that they like less. 

Familiarity should act as a dampener. Scale how far an event moves the other metrics by inverse familiarity. First impressions swing hard; established relationships are stable. One rude act from a stranger hurts more than one from an old friend.
Decay toward a baseline. Without contact, values drift slowly toward neutral (or toward a personality-based default). Trust might decay more slowly than affinity.
Negativity bias. Make negative events weigh about 2–3× as much as positive ones. Betrayal should be hard to undo.
Memory: store events, derive scores

Rather than only incrementing numbers, keep a log of significant interactions per pair ({actor, target, action, valence, magnitude, timestamp}) that gets passed into future conversations between those two characters. This can lead to:
- Callbacks in dialogue (“You still owe me for the bridge incident”)
- Grudges and debts as discrete flags (an unpaid favour, a broken promise, a saved life) that persist even after the numeric score recovers

## The Player

The player can wander around the village and chat to the NPCs. The NPCs can also chat with one another (if they want). When NPCs do chat with one another, their conversations take place in English, at the same pace a normal conversation would take place. If the player is near NPCs who are chatting to one another, they are able to overhear what the NPCs are saying to one another. 

## World

### Size 

Initially the universe might be small - maybe 10 NPCs, as a POC.

The town should have some houses, a coffee shop, a town square and a couple of other amenities. Give it a modern (2026) vibe... possibly erring on futuristic (think Shenzen). 

### News / External Inputs

The town also has a newspaper covering the stories from six feeds: [The Atlantic](https://www.theatlantic.com/feed/best-of/), [OpenAI](https://openai.com/news/rss.xml), [Scientific American](http://rss.sciam.com/ScientificAmerican-Global), [The Economist](https://www.economist.com/the-world-this-week/rss.xml), [RNZ Sport](https://www.rnz.co.nz/rss/sport.xml) and [IGN](https://feeds.feedburner.com/ign/pc-reviews)... the NPCs can, if they wish, check the news on public terminals that are available in the town, and remember where they read each story. 

The village fetches the feeds when it starts and then every hour, and Claude (Haiku, through your Claude Code login) analyses each new story once: up to 10 stories per feed, so about 60 calls on a fresh start. Until the first stories are in, or if the feeds can't be reached, the terminals list 13 real articles bundled in [`content/news/`](content/news/articles.json). `SIMILE_NEWS=0` turns the news off: nothing is fetched or bundled, and the terminals list only the news already stored.

If they read something that triggers them (either it really aligns with one of their core values or it really rubs them the wrong way) they would be likely to bring that up in a conversation with one of the other NPCs or the player ("Hey did you hear the news?" kind of thing). Their likelinees to bring a news story up will depend on how recently they read the article and how strongly it made them feel (negative or positive). 

## Voices

Every NPC speaks out loud in their own voice. Speech is generated locally on the player's machine with [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS), so there's no cloud voice service and no cost per line.

For now the voices are off unless you turn them on (see *Running it*), since the intonation is hard to get right, and each resident only greets you out loud with a line recorded once in their voice.

### Creating an NPC's voice

When an NPC is generated, the generator also writes:
- A **voice description** that fits the character, e.g. "An old man in his seventies. Deep, gravelly voice, speaks slowly and deliberately, gruff but warm." Age and core values should shape it: a high Discipline, high Tradition NPC might speak slowly and formally, a high Adventure, high Optimism one quickly and brightly.
- A **reference line**: a sentence or two (5–10 seconds of speech) that the NPC might say, in character.

The voice design model (`Qwen3-TTS-12Hz-1.7B-VoiceDesign`) turns the description into a recording of the NPC saying their reference line. That clip and its transcript are saved with the NPC and are their voice from then on. This happens once per NPC, when the world is generated.

Voice design doesn't follow accent instructions, though: even "a heavy Irish accent" mostly comes out American. The clone model does keep the accent of a real recording, as long as it's given the recording's transcript. So for an accent, use a recording instead, from ElevenLabs or anywhere else, with its transcript:

1. Drop one clip per resident in `voice-lab/incoming/`, named after the resident's id (`desmond.wav`, `.mp3` or `.m4a`), with a `.txt` of the same name holding exactly the words spoken.
2. Run `voice-lab/import_voices.py`. The transcript becomes the resident's reference line, so it must be 12–25 words with no "!", about 10 seconds of speech, and a clip with a longer transcript is refused. The command converts each clip, checks that it's 5–25 seconds long and that Whisper hears the transcript, then runs the accent check on the clip and on three lines cloned from it. The accent check only warns, since it knows few accents and your ear has the final say. `--dry-run` runs the checks without changing anything. `--force` imports a clip that fails the length or Whisper check, but never one whose transcript breaks the reference line's limits.
3. A clip that passes becomes the resident's voice: their reference line becomes its transcript, and their sample lines are spoken again in the new voice. Voice design won't overwrite it later.

The easiest script to record is the resident's current reference line, which then doubles as the transcript. [`voice-lab/README.md`](voice-lab/README.md#importing-a-recorded-voice) has the commands and the details.

The tone of the reference clip carries into everything the NPC says. A sleepy or angry reference makes a permanently sleepy or angry NPC, so reference lines should be delivered neutrally unless that's the character's fixed mood.

### Speaking in real time

At runtime the clone model (`Qwen3-TTS-12Hz-1.7B-Base`) speaks any new line in an NPC's voice, given their reference clip and its transcript. There's no training step: each NPC's clip is processed once when the game loads and reused for every line.

Each line of dialogue goes through this pipeline:
1. The LLM writes the line, streamed as text.
2. As each sentence completes, it's sent to the clone model with the speaker's voice.
3. Audio streams back in short chunks and plays from the speaker's position in the village, with volume and panning based on their distance from the player.

On an M2 Max, using the MLX version of the model ([mlx-audio](https://github.com/Blaizzy/mlx-audio)) with 8-bit weights, audio starts 0.2–0.4 seconds after a sentence's text arrives, and speech is generated about 3x faster than it plays. The LLM, not the voice, will be the main source of delay.

### Only voicing what the player can hear

Since speech is generated only about 3x faster than real time, one machine can voice just a few conversations at once. That's all the village needs:
- **Every conversation happens as text.** NPCs talk to each other whether or not anyone is listening, and those conversations shape their memories and relationships as usual.
- **Only conversations within earshot are voiced.** When the player walks within earshot, voicing starts with the next line, and it stops when they walk away.
- **Conversations keep normal speaking pace either way.** A line that isn't voiced still takes as long as it would take to say (estimated from its word count), so a conversation lasts the same time whether the player hears it or not.
- **NPC-to-NPC conversations run a line ahead.** Nobody is waiting on the player, so the next reply (text and audio) can be generated while the current speaker is still talking, which avoids gaps between turns. Only NPCs replying to the player depend on the low-latency streaming above.

### Platform

MLX only runs on Apple Silicon. On Windows and Linux the same models would run through Qwen's `qwen-tts` PyTorch package on an Nvidia GPU (untested so far). PyTorch on a Mac is too slow for real time (about 0.7x real time on an M2 Max), so Macs need MLX.

### Open questions

- **Emotion.** The clone model takes no instructions about tone, so delivery comes from the reference clip and the words themselves. Whether an NPC can sound angry in one line and cheerful in the next without their voice changing is untested. One option is a reference clip per mood for each NPC, if the voice design model can keep the voice consistent across them.
- **Model size.** The 0.6B clone model is about 20% faster than the 1.7B. Whether it sounds as good is a call for the ear.
- **Player speech.** If the player talks to NPCs out loud instead of typing, [Whisper](https://github.com/ml-explore/mlx-examples/tree/main/whisper) can transcribe it locally.
