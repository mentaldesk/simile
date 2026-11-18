# simile.loop

S15's loop in stage 2's order (P19), then stage 3's (Q15), played end to end on the fake LLM, in the
sim and in a browser.

## In the sim

`play()` (`playthrough.py`) runs a new village in memory, as `simile.ambient`'s playthrough does,
and a `LoopPlayer` (`player.py`) joins it as a client through the hub. It plays by the client's own
messages alone (`player_move`, `pick_up`, `take`, `sell`, `sell_part`, `sell_recipe`, `fit`, `lamp`,
`eat`, `repair`, `make`, `fire`, `reload`, `stash`, `player_say`). It reads the maps the client
bundles and the `snapshot`, `player_state`, `journal`, `line`, `creature_moved`, `creature_gone`,
`creature_hit`, `machine_changed` and `player_died` messages it's sent, but three things it reads straight from
the server: where the server kept it after a move (`kept`), where a resident is (`approach`) and
whether they're asleep (`awake`). Nothing is handed to it: every recipe is learned and every part
found where the game puts them (`content/street/README.md`'s *Finds*).

**Moving.** It runs the cheapest way its legs and feet allow (`simile.street.moves`), sending where
it is every tenth of a sim second, as the client does every frame or so, and climbing stairs and
ladders, on a street or to another floor, at the client's pace for its legs. Ways in sight of a bot
or a dog on its floor cost more, so it goes over them where it can, as on the metro's train roof
and catwalk. On the way it uses P34's solutions:

- **A bot** coming at it along its floor it jumps, landing well past it.
- **A rat** coming for its food it comes down on, hopping as the rat comes under it.
- **A ladder or a jump onto a floor** waits until no bot, rat or dog is by where it would come onto
  it, off that floor.
- **Bats**: its lamp is on in the dark, as L does, but never in a bat's sight within ten tiles.
- **Light and power**: before each way it checks the lamp lasts the dark there and on to the
  nearest plug from there, and charges first at the nearest plug if it doesn't, or if its power
  cell is under half. It jumps a bot that comes at it while it charges, and goes back to the plug.
- **The lift** down is a way only once it's open: with the datajack, or `lift_open`.

**Stage 2's beats.**

1. **A kidney.** From the square to the clinic, where the doctor tells it the power cell's recipe
   as it walks in, and buys a kidney for 100.
2. **The power cell.** Aris's bench in the maker space teaches it the datajack, and her spares and
   shelf hold parts. On its own legs, while the metro's bots pay a wholly human player no mind, it
   searches the metro's dead appliances and furniture and picks up its secrets and salvage, nearest
   first, selling what no recipe it knows needs and no broken machine's repair uses, so it keeps two
   copper wires for the printer. The shed's lockers give it a ration pack. Then the
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
   dogs' reach, pay for the feet. The hall's ledge also holds the recycler's Apex board, which it
   keeps. Then the metro's high ledge and its 60.
   It leaves the bat cave alone: it has no eye to cross it.
8. **The village reacts.** It finds Aris's notes, and talks to the residents most against bionics
   until one turns it down. Residents who saw its bionics remember them.

`fitted` pays for each bionic, coming back for the salvage while it's short, once everything it
picked up lies there again: a day later, or two for the depot's parts (`REBUILD_RESPAWN`). Then it's
fitted with it. The infrared eye isn't in the loop: its recipe needs the second power cell, whose
parts weigh 10 kg, as much as the player can carry with nothing else, and the lamp weighs 1.

**Stage 3's beats** (`maker.py`), straight after:

1. **The printer.** The metal sheet from the rubble on the metro's disused track, the linear
   actuator from zone 0's crates, and the two wires it kept repair Aris's 3D printer.
2. **The pistol.** Aris's spool on her bench holds 8 plastic: a pistol (6) and a magazine of rounds
   (2), loaded with R's `reload`. It puts the ration pack in the lockers, so rats keep to their nests.
3. **Rats.** From the biggest nest's floor it shoots two as they come in line, a round each.
4. **A dog.** From the den's floor short of its ladder, where the dogs come to the edge of their
   floor and can't reach it, three rounds put one down. Then up the ladder for the delver's two old
   batteries, and a lead pipe on the way back.
5. **The recycler.** The Apex board and the batteries repair it. The pipe presses into 3 plastic, 2
   of it printed into another magazine.
6. **A bot.** It shoots the bot under the metro's catwalk from out of its sight along its floor, six
   rounds, and takes its haul off the ground through `take`, one thing at a time.
7. **Dying on purpose.** It stores the pistol, rounds and plastic in the lockers, since a death
   leaves the stash alone, then stands under zone 0's bats in a room its own legs reach, on no bot's
   floor, and turns the lamp on until they kill it. It wakes in its bed in a whole organic body,
   and rests there until it's healed.
8. **The body.** On its own legs it rides the lift, which stays open, back to the body, and takes
   the money, every bionic and everything else that fits, one `take` at a time. The body goes once
   it's empty. The doctor refits each bionic for a quarter of its credits, the cell first. Anything
   that didn't fit would take another trip; with the pistol in the lockers, nothing's left.
9. **Rounds from scrap.** Home with the body's scrap, the recycler presses it into plastic, and with
   what's in the lockers the printer makes another magazine, loaded.

The batteries come from the den's bedroll, not the second power cell's crates: nothing teaches the
third power cell, whose recipe would use all six, and the loop never learns the second's.

Every coin comes from the kidney, salvage, secrets, finds and recipes, through the ledger. The fake
LLM is `Canned`, the canned one, which has nothing to reflect on and notes each prompt that has a
resident turn the player down. Stage 2 takes about eleven minutes of play in its first sim
morning, unhurt, with the lamp never running flat in the dark. Stage 3 takes about ten more, and
it's hurt only by the bats it gives itself to.

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
| `printer` | at the broken printer, with its parts | E and Enter to repair it, E at Aris's spool, E at the printer for a pistol and rounds, R to load |
| `dog` | on the den's floor short of its ladder | a tap to face the dogs, and X until one is down |
| `bot` | on the metro's floor, out of the bot's sight | a tap to face it, X until it's down, and E at its haul to take it all |
| `stash` | at the lockers, with the pistol | E, and Enter to store the pistol |
| `death` | under the bats | L, until the bats kill them and they wake at home |
| `salvage` | at their body, in a new one | E, and Enter on each thing until the body's gone |
| `refit` | outside the clinic, with their salvaged bionics | the power cell, refitted |
| `recycle` | at the recycler, with the body's scrap | E and Enter for plastic |

```bash
cd client
npx playwright install chromium   # once
node src/loop/loop.e2e.ts         # --saves <dir> plays those instead of the sim's, --beat <name> one, --screens <dir> keeps screenshots
```

The *Loop* workflow runs it on every PR, and the server's tests run the sim's playthrough.
