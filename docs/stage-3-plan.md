# Stage 3 plan: salvage and the maker space

Stage 3 of [Salvage Rights](game-design.md#build-order), after [stage 2's parts, power and
dangers](stage-2-plan.md):

> The house stash, corpses that stay, salvaging your own body, and the maker space's first machines.

Stage 2 gave the tunnels dangers you can only get past. Stage 3 brings Aris's workshop back one
machine at a time. The first, her 3D printer, prints the game's first weapon: a plastic pistol and
its rounds. The second, a recycler, turns the scrap you haul up into the material the printer
needs. Dying stops being a collapse: your body stays where it fell, with everything on it, and
getting back to it is the run.

Each task is one issue and one PR, as sub-issues of a stage 3 tracking issue, with dependencies as
GitHub "blocked by" links.

## The order you get things in

| You have | What opens up | Where it comes from | What it needs |
|---|---|---|---|
| Nothing | The printer and the recycler stand broken in the maker space. E on either shows what it needs | — | — |
| **The printer**, repaired | Printing. Aris left a spool of plastic on the bench: enough for one pistol and a magazine | Your bench in the maker space | A metal sheet, a linear actuator and 2 copper wire. The sheet and actuator are in the tunnels, where stage 2's bionics already reach |
| **A plastic pistol** | Shooting. 6 rounds a magazine: one round kills a rat, three a dog | Printed | Plastic |
| **The recycler**, repaired | Plastic from scrap, so you can print more rounds once Aris's spool is gone | Your bench in the maker space | Its own parts, found deeper than the printer's |
| Better material | Stronger guns and rounds: carbon fibre, then metal | Salvaged further on | A machine that can work it: later stages |

## Decisions

| Decision | Choice |
|---|---|
| **Repairing a machine** | It takes parts, like a bionic recipe but without a recipe to find: E at a broken machine lists what it needs and what you have of each, and repairs it once you have them all. The printer needs a metal sheet, a linear actuator and 2 copper wire. |
| **The pistol** | Limited damage. It holds 6 rounds. One round kills a rat, three kill a dog. |
| **Rounds** | Printed, not bought. Printing takes material, and the material decides the damage: plastic first, then carbon fibre, eventually metal. |
| **The recycler** | The maker space's second machine. It turns scrap into the printer's material. |
| **Implant parts** | The printer doesn't make them yet. |
| **Death** | Death replaces stage 2's collapse. Health at none is death. Hunger at none starts to hurt: you take damage regularly until you eat, and starve to death if you don't. Once the power cell is in, power at none is death too, since you can't move. |
| **The new body** | You wake in your bed in a whole, organic body with no bionics, as the design says. Everything in it can be sold again, so the kidney is always a little cash to start over with. |
| **Material** | An item you carry and stash, by kind (`plastic` for now) and amount. A pistol costs 6 plastic and a magazine of 6 rounds costs 2. Aris's spool holds 8. The recycler turns each kilo of scrap into 1 plastic. |
| **Wear** | A plastic pistol wears out after 30 rounds, as the [design](game-design.md#dangers) has it ("lasts a few shots"), so plastic stays a beginner's gun. Its condition shows on the item. |
| **Recycler bots** | They take 6 rounds, a whole magazine, and drop everything they collected when destroyed. Height is still the cheap way past them. |
| **Your corpse** | It stays where you died, with your money, everything you carried and every bionic you had fitted. Dying again before you reach it leaves a second corpse, and both stay. |
| **Salvaging your own body** | E at your corpse takes the money and the items. Bionics come out as parts you carry: `bionic` items with their grade. The clinic refits a salvaged bionic for a fitting fee, with no recipe parts, since its recipe is still in your mind. |
| **The stash** | Your home is the maker space, so the stash is Aris's lockers there. E puts things in and takes them out. It holds 20 kg to start. Fitting it out to hold more is a later task. |
| **What the village sees** | Carrying a pistol is a fact residents notice, like a bionic. Security and Tradition distrust it, as they already distrust bionics. |

## Architecture additions

- **Machines** are maker-space interactables with a state, `broken` or `working`, and the parts a
  repair needs. They're in the snapshot. A working machine offers what it can make, priced in
  material.
- **Weapons** are items with rounds loaded and a condition. **Rounds** and **material** are
  stackable items with an amount.
- **Shooting** is a client action: fire in the direction you face. The server resolves it as a
  hitscan along the row, as far as the first creature or wall in range, and damages that creature.
  The client draws the flash and the hit. Creatures get health, and stage 2's kick takes it too.
- **Corpses** are interactables like stage 2's piles, holding money, items and bionics, and marked
  as yours.
- **The stash** is a store on the player beside what they carry, with its own limit.

## Tasks

### Contracts first, each its own small PR

They share files, so they go one at a time.

| ID | Task | Done when |
|---|---|---|
| Q1 | **Items, material and weapons:** stackable items with an amount; `material` and `weapon` kinds; a weapon's rounds loaded and condition; `bionic` items with a grade, for salvaged bionics; the stash's contents and limit on the player. | Schema, protocol and generated types merged. Stage 2 saves load. |
| Q2 | **Machines and corpses:** a machine's kind, state and repair parts; what a working machine makes and for how much material; a corpse holding money, items and bionics. In the snapshot and in delta messages. | Schema and protocol merged, with fixtures. |
| Q3 | **Shooting and death:** the client's `fire`, `reload`, `repair`, `make` and `stash` messages; a hit event; creature health in the creature delta; `player_died` in place of `player_collapsed`. | Schema and protocol merged. |

### Then, in parallel where their paths allow

| ID | Track | Task | Depends on |
|---|---|---|---|
| Q4 | Maker space | **Repairing machines:** the printer and the recycler stand broken in the maker space; E lists what each needs against what you carry, and repairs it when you have it all; repairs are saved. | Q2 |
| Q5 | Maker space | **The printer:** E at a working printer offers a plastic pistol and a magazine of rounds for their plastic; Aris's spool of plastic is on the bench. The UI is the clinic's list, with icons. | Q1, Q4 |
| Q6 | Maker space | **The recycler:** E at a working recycler turns the scrap you carry into plastic, by weight. | Q1, Q4 |
| Q7 | World | **Parts in the world:** the metal sheet and the linear actuator where stage 2's bionics reach (the sheet in the metro, the actuator in sewers zone 0 or 1); the recycler's parts deeper in. Generated sewers checked to hold each where it's reachable. | Q2 |
| Q8 | Combat, client | **Shooting:** fire and reload keys; the server's hitscan along the row; damage by material; creature health (a rat takes 1 round, a dog 3, a bot 6, and kicks still hurt as in stage 2); a muzzle flash, a hit flash and a flinch; the pistol wearing out. | Q1, Q3 |
| Q9 | World | **Destroying recycler bots:** a destroyed bot drops everything it collected as a pile. | Q8 |
| Q10 | Player | **Death and the corpse:** death replaces collapse. Starving hurts regularly until you eat, and power at none kills. A death leaves a corpse with your money, items and bionics where you fell, and you wake in your bed in a whole organic body whose parts can all be sold again. | Q1, Q2, Q3 |
| Q11 | Player, clinic | **Salvaging your own body:** E at your corpse takes everything, bionics as parts; the clinic refits a salvaged bionic for a fitting fee. | Q10 |
| Q12 | Player, client | **The stash:** E at the maker space's lockers stores and takes things, up to its limit; what's in it shows on the character screen. | Q1 |
| Q13 | Art | **Machines, weapons and corpses:** the printer and recycler, broken and working, in the village's clean style; icons for the pistol, rounds, plastic, metal sheet, linear actuator and salvaged bionics; the player's figure holding and firing the pistol; your corpse. | Q1, Q2 |
| Q14 | Story | **Residents notice the pistol:** carrying one is a fact in what residents see of you, and Security and Tradition react to it as they do to bionics. | Q1 |

### Last

| ID | Task | Done when |
|---|---|---|
| Q15 | **The loop, end to end:** stage 2's playthrough, then: find the sheet and the actuator, repair the printer, print a pistol from Aris's spool, shoot rats and a dog, destroy a bot for its haul, die on purpose, wake whole, go back, salvage your body, refit a bionic, and haul scrap home to recycle into rounds. | It passes in CI on the fake LLM. The user plays it. |

## Later

- **Carbon fibre and metal** guns and rounds, and the machines that work them.
- **The printer making implant parts.**
- **Fitting out the stash** to hold more, and the maker space's other machines: the laser cutter,
  the loom and the sewing machine.
- **Charges** that open walls, and **sonar** for the bats.
- **Snakes, organ cultures and radioactive waste**, which come with the deeper sewers.
- **Companions**, which are [stage 4](game-design.md#build-order).
