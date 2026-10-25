# Stage 2 plan: parts, power and dangers

Stage 2 of [Salvage Rights](game-design.md#build-order), after [stage 1's loop](stage-1-plan.md).
Stage 1 made it too easy to get stuck: the kidney's money buys the wrong legs as easily as the right
ones, and only the datajack reaches the sewers. Stage 2 gates each bionic on parts found where you
can reach them with what you have, and adds the first [dangers](game-design.md#dangers) to get past.

Each task is one issue and one PR, as sub-issues of a stage 2 tracking issue, with dependencies as
GitHub "blocked by" links.

## The order you get things in

| You have | What opens up | Where the recipe is | Where the parts are |
|---|---|---|---|
| Nothing | The village and the metro. You can sell a kidney and talk to the doctor, but there's nothing to buy yet | — | — |
| **Power cell**, for the stomach | Every other bionic. You stop eating | The doctor tells you: nothing she fits runs without one | The village and the metro |
| **Datajack**, for a vertebra | The lift to the sewers, terminals, old machinery | Aris's schematic, on her bench in the maker space | 3 copper wire and a USB-C connector: the connector and a wire in the maker space's furniture, two wires in the metro's dead appliances. And 100 credits |
| **Bionic legs**, for the legs | Running faster, jumping further, kicking harder, and the sewers' gate | Sewers zone 0 | Sewers zone 0 |
| **Spring feet**, for the feet | Higher ledges, including the metro's high ledge | Sewers zone 1 | Sewers zone 1 |
| **Infrared eye**, for an eye | Seeing a liar's flush, and seeing in the dark without the lamp | A terminal in a security station deep in the sewers | One part from a villager, who gives it only if they trust you |
| Bigger cells, better legs and feet | Running more bionics, and catching up with the dogs | Further on | Further on |

## Decisions

| Decision | Choice |
|---|---|
| **Recipes** | Knowledge, not items: they're in the mind, so they survive collapse and, later, death. A recipe lists its parts and credits. The clinic fits only what you have a recipe for. |
| **Selling recipes** | The clinic buys each recipe once, for a one-off sum. You still know it, and can't sell it again. |
| **Parts** | Tradable. The trader buys them and sells back what you sold at 2× the price, so selling a part never leaves you stuck. Furniture and appliances are searched once and don't refill. |
| **The kidney** | It pays for the power cell. The cell costs about what the kidney fetches, more than the metro gives a player on foot in a day or two. The recycler bots taking salvage keeps that grind slow. |
| **The power cell** | Goes in place of the stomach. Hunger becomes power: it drains, faster with each bionic fitted, and charges at plugs. A cell runs a limited number of bionics, so more bionics need a bigger cell. |
| **Legs and feet** | Two parts, two lines of upgrades: the legs for speed (and kick), the feet for jump height. The body gets a `feet` slot. Stage 1's five grades of legs fold into the two lines, and the Apex actuator goes to the top grade of the legs. |
| **The sewers' gate** | Passable with the bionic legs, over its gap. The weir's height waits for the feet, from zone 1. |
| **Health** | A new vital. Dangers take it, it comes back slowly, faster at home, and the clinic patches you up for money. At none you collapse and wake at home, as when you starve. |
| **Effects** | Ailments with a cause and a rate of fading. Stage 2's is an infected rat bite; the radiation dose comes with the deeper sewers. One kidney makes either fade more slowly. |
| **Kicking** | The only attack until the maker space makes weapons. It hurts rats and little else. |
| **The lamp** | A plug charges it from flat to full in about 3 real seconds. Waiting isn't the game; getting to a plug is. The player's own power charges as fast. |

## Architecture additions

- **The player's mind** is new state beside the body: known recipes, and which have been sold. It
  survives collapse and is kept through stage 3's death.
- **Creatures** are sim entities, like residents but much simpler: a position, a kind, a state, and
  a way of moving (patrol, chase, flee light, drawn to food or light). They're facts in the sim,
  ticked on the loop and sent to the client, which draws and animates them.
- **Searchable things** are map interactables holding items, searched once with E, like a pickup
  with a look of its own.

## Tasks

### Contracts first, each its own small PR

| ID | Task | Done when |
|---|---|---|
| P1 | **Body, bionics and the mind:** `stomach` and `feet` body slots; the power cell, legs and feet lines and the eye as bionics, with stage 1's leg grades mapped onto them; a `Recipe` (parts with counts, credits, what it replaces, what it needs fitted first); known and sold recipes on the player. A protocol message for the mind. | Schema, protocol and generated types merged. Stage 1 saves load, their legs mapped. |
| P2 | **Vitals:** health, power (in place of hunger once the cell is fitted), and effects (a kind, a strength and how fast it fades). In `player_state`. | Schema and protocol merged. Old saves load at full health with no effects. |
| P3 | **Creatures and searchable things:** a creature's kind, position, facing and state, in the snapshot and in a delta message; a searchable interactable holding items, and whether it's been searched. | Schema and protocol merged, with fixtures. |

### Then, in parallel where their paths allow

| ID | Track | Task | Depends on |
|---|---|---|---|
| P4 | Economy | **Recipes at the clinic:** the doctor fits only known recipes, for their credits and parts, and only once the power cell is in (the cell itself excepted). She buys each recipe once. Her prompt follows what you know, so she can tease what she could do without listing it. | P1 |
| P5 | Economy | **Trading parts:** the trader buys parts at the economy's prices and sells back what it bought at 2×. | P1 |
| P6 | World | **Recipes and parts in the world:** the doctor's power cell recipe; Aris's datajack schematic on her bench; the maker space's furniture and the metro's dead appliances to search, holding the datajack's parts and the cell's; the legs' recipe and parts in sewers zone 0, the feet's in zone 1, the eye's recipe at a sewers security terminal (a jack). Generated sewers checked to hold each where it's reachable with what you'd have. | P1, P3 |
| P7 | Behaviour | **Power:** hunger becomes power once the cell is fitted; drain grows with each bionic; charging at plugs; a cell's limit on bionics; the lamp and the player charging in about 3 seconds. Meals stop being on offer to a cell. | P1, P2 |
| P8 | World, client | **Legs and feet:** speed and kick from the legs, jump height from the feet, each by grade; the sewers' gate passable with the legs; the metro's high ledge reached with the feet. | P1 |
| P9 | Behaviour, client | **Health and kicking:** taking damage, healing, the clinic patching you up, collapsing at none; a kick, harder with the legs; a rat bite that can turn infected; effects fading, slower with one kidney. | P2 |
| P10 | Sim, client | **Creatures:** the engine every creature uses, ticked on the loop: moving by tiles and ladders as their kind allows, the ways of moving above, hurting on contact, taking kicks. The client draws them from P3's messages. | P3, P9 |
| P11 | Art | **Creature figures:** rats, recycler bots, wild dogs, bats and snakes, painted in the tunnels' cartoon, with a walk or fly cycle and an attack. | — |
| P12 | World | **The metro's rats and recycler bots:** rats drawn to carried food; bots that collect the metro's salvage and ignore a wholly human player. | P10, P11 |
| P13 | World | **Wild dogs:** few, in sewers zone 0, faster than the player on any legs stage 2 has, unable to climb ladders or pass doors. | P10, P11 |
| P14 | World, client | **Bats and the dark:** bat caves in the sewers that attack while the lamp is on; the infrared eye showing the dark without it. | P10, P11 |
| P15 | Client | **The character screen:** vitals (power or hunger, health, the lamp, credits, effects), the body (each part present, sold or bionic) and what you carry against the limit, with the mind's recipes and what you have of each. | P1, P2 |
| P16 | Story | **The eye's part from a villager:** a resident who has it, chosen by values, and gives it once they trust you enough. | P1 |

### Last

| ID | Task | Done when |
|---|---|---|
| P17 | **The loop, end to end:** S15's playthrough in the new order. Sell the kidney, learn and fit the cell, find the schematic and the datajack's parts, fit it, take the lift, slip past a dog, fit the legs, cross the gate, find the feet, reach the metro's high ledge, kick some rats. | It passes in CI on the fake LLM. The user plays it. |

## Later

Snakes, organ cultures and radioactive waste are in the [design](game-design.md#dangers) but wait
for the next stage's deeper sewers, as do the weapons, the sonar and destroying a recycler bot for
its haul.
