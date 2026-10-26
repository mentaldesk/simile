# simile.loop

S15: stage 1's loop, played end to end on the fake LLM, in the sim and in a browser.

## In the sim

`play()` (`playthrough.py`) runs a new village in memory, as `simile.ambient`'s playthrough does,
and a `LoopPlayer` joins it as a client through the hub. It plays by the client's own messages
alone (`player_move`, `pick_up`, `sell`, `sell_part`, `fit`, `lamp`, `eat`, `player_say`), and knows
of itself only the `player_state`, `journal` and `line` messages it's sent. It runs along the maps'
routes at the client's running pace, with the jumps its legs allow (`simile.street.moves`), and
lights its lamp in the dark.

1. **A kidney.** From the square to the clinic, where it sells a kidney for 100.
2. **The legs and a secret.** The high ledge is out of reach on its own legs. It's fitted with the
   hydraulic legs and picks up the ledge's 60.
3. **The datajack and the lift.** It picks up the metro's secrets and salvage, nearest first,
   selling once nothing more fits, until it can pay for the datajack's credits. The server refuses it the
   sewers until it's fitted. Then the dead terminal gives up `lift_log`, and the lift takes it down.
4. **The sewers' clue.** The hatch is out of reach on its own legs, and gives up `hatch_log`. It
   gathers the sewers' salvage and comes back up to sell it.
5. **The eye and a lie.** It does a round of the metro and the sewers each day, skipping the time
   until the salvage lies there again, until it can pay for the eye. Then it asks an attacker
   where they were the night Aris was attacked. Their alibi flushes, and the journal marks it.
   The attacker it asks is one who stays put for two minutes in the world served from the eye
   beat's save (`Saves.stays`), since a save keeps less of what someone's doing than the sim, and
   the browser takes a while to get there.
6. **The village reacts.** It finds Aris's notes, and talks to the residents most against bionics
   until one turns it down. Residents who saw its bionics remember them.

**A stand-in until P6 and P19** (`stand_in.py`): the clinic now fits the datajack and the eye only
from a known recipe, with its parts, once a power cell is in, and nothing in the world teaches a
recipe or holds those parts yet. So before each, the loop fits the cell, teaches the recipe and
hands over its parts, straight into the server's player. P19 replays the loop in stage 2's order
and deletes it.

Every coin comes from the kidney, salvage and secrets, through the ledger. The fake LLM is
`Covers`, the canned one, except that a resident set up to lie about where they'd been gives their
alibi word for word, so the eye catches it. It takes about two sim days, almost all of them waiting
for salvage: about ten minutes of play.

```bash
cd server
uv run simile loop play                  # what happened, and how long it took
uv run simile loop play --saves <dir>    # and the world before each of the browser's beats
```

## In the browser

`client/src/loop/loop.e2e.ts` plays the visible beats in Chromium, by the keys, against the real
client and a real server on the fake LLM. It runs `simile loop play --saves` first, then starts
each beat from its save with `simile loop serve`, which serves a copy of the world with `Covers`
and the player where the beat starts:

| Beat | From | By the keys |
|---|---|---|
| `kidney` | outside the clinic, on day 0 | E into the clinic, E for its panel, sell a kidney and be fitted with the legs, ↑ out, the run jump onto the high ledge, E for its secret |
| `datajack` | outside the clinic, with the datajack's price | the datajack, E at the dead terminal for its log in the journal, E down the lift and back up |
| `hatch` | beside the sewers' hatch | E for its log in the journal |
| `eye` | beside the attacker, with the eye | E and the question, the flush on their alibi, J for the journal's mark |

```bash
cd client
npx playwright install chromium   # once
node src/loop/loop.e2e.ts         # --saves <dir> plays those instead of the sim's, --beat <name> one, --screens <dir> keeps screenshots
```

The *Loop* workflow runs it on every PR, and the server's tests run the sim's playthrough.
