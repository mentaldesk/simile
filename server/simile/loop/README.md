# simile.loop

S15's loop in stage 2's order (P19), played end to end on the fake LLM, in the sim and in a browser.

## In the sim

`play()` (`playthrough.py`) runs a new village in memory, as `simile.ambient`'s playthrough does,
and a `LoopPlayer` (`player.py`) joins it as a client through the hub. It plays by the client's own
messages alone (`player_move`, `pick_up`, `sell`, `sell_part`, `sell_recipe`, `fit`, `lamp`, `eat`,
`player_say`). It reads the maps the client bundles and the `snapshot`, `player_state`,
`journal`, `line` and `creature_moved` messages it's sent, but three things it reads straight from
the server: where the server kept it after a move (`kept`), where a resident is (`approach`) and
whether they're asleep (`awake`). Nothing is handed to it: every recipe is learned and every part
found where the game puts them (`content/street/README.md`'s *Finds*).

**Moving.** It runs the cheapest way its legs and feet allow (`simile.street.moves`), sending where
it is every tenth of a sim second, as the client does every frame or so, and climbing at the
client's pace. Ways in sight of a bot or a dog on its floor cost more, so it goes over them where it
can, as on the metro's train roof and catwalk. On the way it uses P34's solutions:

- **A bot** coming at it along its floor it jumps, landing well past it.
- **A rat** coming for its food it comes down on, hopping as the rat comes under it.
- **A ladder or a jump onto a floor** waits until no bot, rat or dog is by where it would come onto
  it, off that floor.
- **Bats**: its lamp is on in the dark, as L does, but never in a bat's sight within ten tiles.
- **Light and power**: before each way it checks the lamp lasts the dark there and on to the
  nearest plug from there, and charges first at the nearest plug if it doesn't, or if its power
  cell is under half.

**The beats.**

1. **A kidney.** From the square to the clinic, where the doctor tells it the power cell's recipe
   as it walks in, and buys a kidney for 100.
2. **The power cell.** Aris's bench in the maker space teaches it the datajack, and her spares and
   shelf hold parts. On its own legs, while the metro's bots pay a wholly human player no mind, it
   searches the metro's dead appliances and furniture and picks up its secrets and salvage, nearest
   first, selling what no recipe it knows needs. The shed's lockers give it a ration pack. Then the
   cell, in place of its stomach.
3. **The datajack.** The server refuses it the sewers until it's fitted. Then the dead terminal
   gives up `lift_log`, and the lift takes it down.
4. **Rats.** On the floor of the biggest nest with the ration pack, it comes down on each rat as it
   comes for it.
5. **The legs.** Zone 0's delver's bedroll and crates, past the bots and the bats' roosts with the
   lamp off, hold the legs' recipe and parts. With the zone's secret and salvage, and the recipes it
   knows sold to the doctor, they pay for the legs.
6. **The gate.** Over the gap on the legs, and on to the hatch, which gives up `hatch_log`.
7. **The feet.** Zone 1's bedroll and crates, and the hall's ledge and the den's stash, out of the
   dogs' reach, pay for the feet. Then the metro's high ledge and its 60.
   It leaves the bat cave alone: it has no eye to cross it.
8. **The village reacts.** It finds Aris's notes, and talks to the residents most against bionics
   until one turns it down. Residents who saw its bionics remember them.

`fitted` pays for each bionic, coming back a day later for the salvage while it's short, and is
fitted with it. The infrared eye isn't in the loop: its recipe needs the second power cell, whose
parts weigh 10 kg, as much as the player can carry with nothing else, and the lamp weighs 1.

Every coin comes from the kidney, salvage, secrets, finds and recipes, through the ledger. The fake
LLM is `Canned`, the canned one, which has nothing to reflect on and notes each prompt that has a
resident turn the player down. The loop takes about eleven minutes of play in its first sim
morning, unhurt, with the lamp never running flat in the dark.

```bash
cd server
uv run simile loop play                  # what happened, and how long it took
uv run simile loop play --saves <dir>    # and the world before each of the browser's beats
```

## In the browser

`client/src/loop/loop.e2e.ts` plays the visible beats in Chromium, by the keys, against the real
client and a real server on the fake LLM. It runs `simile loop play --saves` first, then starts
each beat from its save with `simile loop serve`, which serves a copy of the world with `Canned`,
the player where the beat starts and residents who choose by a seed:

| Beat | From | By the keys |
|---|---|---|
| `kidney` | outside the clinic, on day 0 | E into the clinic, E for its panel, sell a kidney |
| `cell` | outside the clinic, with the cell's parts and price | the power cell |
| `datajack` | outside the clinic, with the datajack's parts and price | the datajack, E at the dead terminal for its log in the journal, E down the lift and back up |
| `legs` | outside the clinic, with the legs' parts and price | the bionic legs |
| `gate` | on the walkway, at the gap | back for a run-up, and the run jump over the gap |
| `hatch` | beside the sewers' hatch | E for its log in the journal |
| `feet` | outside the clinic, with the feet's parts and price | the spring feet, E out, the jump onto the high ledge, E for its secret |

```bash
cd client
npx playwright install chromium   # once
node src/loop/loop.e2e.ts         # --saves <dir> plays those instead of the sim's, --beat <name> one, --screens <dir> keeps screenshots
```

The *Loop* workflow runs it on every PR, and the server's tests run the sim's playthrough.
