# Demo: the Mars story

A scripted, repeatable morning in the village. A real article about terraforming Mars is on the news
terminals, and it splits the residents along their values: the adventurous and ambitious love it,
while those who care most about compassion, tradition and peace of mind would rather the money went
on this planet first. The player overhears them argue about it in their own voices, talks to a
couple of them, and watches their relationships move in the debug overlay.

## Running it

You need:

- A Mac with Apple Silicon for the voices (Qwen3-TTS on MLX). Elsewhere it runs unvoiced, with text
  bubbles only.
- [uv](https://docs.astral.sh/uv/), Node 22.12+ and make, as for `make dev`.
- Claude Code installed and logged in. Every call goes through L1 on that login; no API key.
- About 3 GB of memory for the voice model. The first run installs the `voice` extra (`mlx-audio`)
  and downloads the model from Hugging Face, about 3 GB.

```bash
demo/run.sh
```

It rebuilds the demo database (`server/data/demo.db`) from this folder, then starts the sim server
with `SIMILE_VOICE=1` on port 8000 and the client on 5173. When it says the village is running, open
<http://localhost:5173> and click into the page or press a key: browsers keep audio muted until
then. The residents start acting as soon as the server is up, so have the page open by then. It
reconnects on its own, so you can open it while the voice model loads. Ctrl-C stops both.

| Variable | Default | |
|---|---|---|
| `DEMO_DB` | `server/data/demo.db` | The database to rebuild. Your normal village in `simile.db` is never touched. |
| `SIMILE_PORT`, `CLIENT_PORT` | 8000, 5173 | Ports, to run it next to `make dev`. |
| `SIMILE_VOICE` | 1 | 0 runs it unvoiced. |

`SIMILE_NEWS` is turned off, so the Mars article is the only news and nothing is fetched or
analysed.

**Resetting** is running `demo/run.sh` again: every run starts from the same state. To carry on
from where a demo stopped instead (the server saves on Ctrl-C), run the village on the demo database:
`SIMILE_DB="$PWD/server/data/demo.db" SIMILE_VOICE=1 make dev`. Don't use `simile reset` or
`SIMILE_FRESH=1` on it: they forget who has read the article.

## The walk-through (2 to 3 minutes)

Times are from the moment the server is up. Lines quoted are from a real run; yours will differ.

1. **0:00, the square.** You start south of the fountain. On your left, Tobias walks over to Kofi
   and opens on the Mars story within about 10 seconds. Stand still and listen. Tobias, the
   retired lockkeeper: "I'd sooner we looked after the one world we have before we set about
   remaking another." Kofi, the mural painter: "What if they clean up Earth too? Half the walls in
   this square could use a fresh coat of hope." Their chat runs about a minute.
2. **0:20, inside their heads.** Press <kbd>`</kbd> and click Tobias. The overlay shows his goal
   (`talk kofi`), his last decision (seeking out Kofi scored 1.17, going home 0.66), his memory of
   the article (feeling −0.60), and his relationships: everyone at the same first impression, with
   familiarity 0.15. Then click Kofi, whose memory of it is the opposite (+0.85), and leave the
   overlay on him.
3. **0:45, the coffee shop terrace.** Walk north (up arrow, a few seconds). Desmond, the tenants'
   rights caseworker, is telling Marguerite, the patent strategist, that the money should go to
   housing; she calls Mars research "a rounding error beside housing budgets". Theirs is short, so
   you'll catch the end.
4. **1:00, Desmond.** Still lonely, Desmond may come over and greet you ("Kia orana. Mind if I
   sit?"). Press Enter and ask him about Mars, or walk on. About 10 seconds after Kofi and Tobias
   finish, once the reflection lands, Kofi's row for Tobias jumps to the top of his table: like
   0.71 → 0.82, familiarity 0.15 → 0.20. They disagreed about Mars and came away liking each other
   more.
5. **1:20, Raymond at the terminal.** Walk east along the square, then south to the news terminal
   on its east edge, by the park gate. Raymond, the franchise broker, walked there at the start and
   read the article live: click him to see the new memory ("Frankly, Mars is the biggest territory
   nobody has franchised yet"). Press Enter and say "Morning, Raymond. Anything good on the terminal
   today?", then push back: "Mars? Isn't that money better spent down here?" ("The principle is the
   same whether it's Mars or the village: you identify the gap, you scale the solution.")
6. **2:00, Henrietta in the park.** A few steps east, through the gate. Press Enter: "Henrietta,
   have you heard they want to make Mars liveable?" ("Mars has no planning permission and no
   residents' association.") Then "Raymond says it's the future. You're not tempted?" She'll be done
   with you quickly.
7. **2:30, what Raymond makes of you.** Talking to Henrietta ended your chat with Raymond. Click
   him again (by the terminal, or heading for the coffee shop): there's a new row for Player, with
   like and respect a little below his first impression (0.47 and 0.40, from 0.50 and 0.45) after
   you argued with him.

The village carries on after that: in the real run Tobias, still lonely, sought out Odalys, who
told him about the Mars piece over breakfast talk.

## What it starts from

[`scenario.json`](scenario.json) and [`article.json`](article.json) hold everything, and
[`prepare.py`](prepare.py) writes them into a fresh database.

- **The time** is 10:30 on 16 October 2026, the morning after the article came out.
- **The article** is "What would it take to terraform Mars? Erika DeBenedictis has ideas",
  [Scientific American](https://www.scientificamerican.com/article/what-would-it-take-to-terraform-mars-erika-debenedictis-has-ideas/),
  15 October 2026, picked from the live feeds. Its summary is our own paraphrase of the feed's.
  It's pre-analysed: X1's analysis call rated it knowledge 0.6, optimism 0.6, adventure 0.5,
  creativity 0.3 and ambition 0.3, tone +0.4.
- **Who has read it.** Nine of the ten, each with the take B4's reaction prompt gave them in one
  real run, read between 08:20 and 10:10. They bring it up through B2's "news you might bring up".
  Raymond hasn't read it; his need for news is high, so he goes and reads it at the start.

  | Resident | Feeling | Strength | Their take, in short |
  |---|--:|--:|---|
  | kofi | +0.85 | 0.8 | Already sketching murals for Mars |
  | ingrid | +0.8 | 0.7 | A whole planet as a prototype; jealous it isn't hers |
  | priya | +0.7 | 0.8 | Mars with a cocktail bar on it |
  | marguerite | +0.6 | 0.6 | A patentable platform, if the economics hold up |
  | odalys | +0.3 | 0.4 | Lovely, but half the village can't afford supper |
  | lachlan | +0.2 | 0.1 | Good on her; he'd rather the kids turned up to training |
  | henrietta | −0.2 | 0.15 | No residents' association, no planning permission, no view |
  | desmond | −0.2 | 0.3 | Put that energy into housing first |
  | tobias | −0.6 | 0.4 | Look after the one world we've got |

- **Where everyone is.** Tobias by the west lamp of the square and Kofi near him; Desmond and
  Marguerite on the coffee shop terrace; Raymond in the square's south-east corner; Henrietta in
  the park by the gate; Ingrid and Priya at the maker space; Lachlan in the park; Odalys at the
  noodle bar. Tobias and Desmond are as lonely as can be (social need 1.0) and decide on the first
  think, so each seeks out the nearest person. Everyone else is mid-stay, between 3 and 40 minutes
  from their next decision.
- **Everyone has met.** Each resident's relationship with every other is R1's first impression
  (`meet`, from their own values) with familiarity 0.15, so the overlay lists them all from the
  start and you can watch a row move.

## Claude usage

The run behind the quotes above took 36 calls over the 4 sim minutes it ran (the walk-through plus
a minute): 23 conversation lines (Haiku 5.5), 7 reflections (Haiku 5.5), 5 player replies (Haiku
4.5) and 1 news reaction. That's $0.02 API-equivalent, and the five-hour usage window went from 22%
to 23%. Leaving it running costs more: the scripted loneliness keeps conversations coming for the
first few minutes, and after that D2's soak measured about 43 calls a sim hour.

## Checking it without Claude

```bash
cd server && uv run python ../demo/check.py --runs 20
```

Runs the opening headless on the fake LLM and counts how often each scripted beat happens: Tobias
seeking out Kofi, Desmond seeking out Marguerite, both conversations starting, and Raymond going to
read. 100 runs out of 100 went to script, the conversations starting 7 sim seconds in. Run it after
changing `scenario.json`, or after B1 or B2 change. It exits non-zero if any beat was missed.

## Recording

The recording needs a person: run the demo, follow the walk-through, and capture 2 to 3 minutes of
the browser with its sound. Check that the recording has the system audio and not just the
microphone: OBS's macOS Screen Capture source records it, and QuickTime needs a loopback device such
as BlackHole.
