# simile.player

S5: the player gets hungry. S6: salvage, and selling it. The player's state is `player_of(app)`
(`simile.persistence`), saved with the world. This module changes it at runtime and tells the
client: its `running` hook joins the player to the economy, makes a `Hunger`, `Pickups`, a `Trade`
and a `PlayerSync`, and ticks `Hunger` and `PlayerSync` on the sim loop.

## Hunger

- **It rises** by `rise` (0.25) a sim hour, from fed (0) to collapsing (1) in four hours, but only
  while a client is in the game: one that has sent a player position since it connected
  (`InGame`). Nobody starves while the game is closed or on the menu or the character creator, and
  `simile headless` and `simile behaviour simulate` never change the player.
- **Eating** is the client's `eat` (`docs/protocol.md`):
  - **At home**, anywhere in the building, a meal is free and relieves `home_meal` (all of it).
  - **At a shop** in `meals`, the café or the noodle bar, anywhere in the building, a meal costs
    the economy's meal price for that shop (5 at the Daily Grind, 10 at the noodle bar) and
    relieves the shop's `meals` share (0.5 and 1). It's on offer only while the shop would feed a
    resident, by B1's `supply` hook: the café while its barista is on shift, the noodle bar while
    its keeper is in and their batch lasts. The player pays the keeper through the ledger as
    `PLAYER` (`simile.economy`'s *The player*), and the keeper pays the supplies as for any sale.
    A noodle-bar meal comes out of the batch.
  - **Food they carry** relieves `food` (0.4) an item.
  - `meal()` is the meal on offer where they stand, which goes to the client in `player_state` so
    its hint can offer it. Ordering a drink at the café's counter is unchanged and free.
- **Collapsing.** At 1 they collapse. Everything they carry but the lamp is left in a `Pile` where
  they fell, on the ground below if they were mid-air or partway up stairs or a ladder, at the end
  of `Player.left`. They wake at home, the entry of `home`, with hunger `waking` (0.75), and the
  client gets `player_collapsed` to put them there. The lamp and their money stay with them, so
  they can see to go back for the rest.

Home is `PlayerConfig.home`, the maker space: the village has no house for the player, and every
house is someone's. Aris's workshop is the place the story makes theirs until one is added.

## Salvage and secrets

`Pickups` has what lies in the world for the player to pick up:

- **Salvage** lies at the maps' `salvage` pickups (`TownMap.pickups`, from each map's `pickups`
  layer). A pickup names its item in the map, as a secret does, so generated levels such as S9's
  sewers can say what lies where. The metro's six (S3) don't, so `PlayerConfig.salvage` says what
  lies at each, by pickup id:

  | Pickup | Where | Salvage | kg |
  |---|---|---|--:|
  | `metro_salvage_1` | On the dead train's roof | Copper wire | 1.5 |
  | `metro_salvage_2` | The west tunnel | Scrap steel | 4.5 |
  | `metro_salvage_3` | The west tunnel | Circuit board | 0.5 |
  | `metro_salvage_4` | The pipe ledge | Brass valve | 2 |
  | `metro_salvage_5` | The east tunnel | Signal relay | 1 |
  | `metro_salvage_6` | The high ledge, for the legs | Servo motor | 3 |

  That's 12.5 kg, and with the lamp they carry 9 kg more, so it takes more than one trip.
- **Secrets** are `secret` pickups holding money, an item or both, as the map says: 25, 40 and 60
  money and a ration pack in the metro, the 60 on the high ledge only the hydraulic legs reach.
- **Picking up.** The client's `pick_up` takes from the nearest pile within `reach` (1.5 tiles) on
  the map they're on, one they left or one lying at a pickup: its money, and each item that still
  fits under their carry limit, in order. Money weighs nothing, and goes through the ledger as
  `found`. Taking from a pickup records when, by its id, in `Player.taken`, which is saved, and
  whatever of it didn't fit becomes a pile of theirs at the end of `left`. Any that don't fit of
  one of theirs stay in it.
- **One thing per press.** Other modules add what else `pick_up` can take to `claimers_of(app)`,
  such as S13's clues, each a `Claim` with its distance from the player. `pick_up` takes the
  nearest claim if it's nearer than any pile in reach, and the pile otherwise, a tie included.
  Never both.
- **The jacks** (`machines.py`, S8) are the machines only the datajack works: the metro's dead
  terminal and its lift. With the datajack fitted, standing on a jack's stand tile is a claim on
  `pick_up` that writes each fact found in it to the journal, as a clue does, and sends `journal`.
  The terminal holds the incident's `lift_log`. Without the datajack it claims nothing. The lift's
  link to the sewers is the client's to lock, as the server doesn't check doors.
- **Salvage comes back; secrets don't.** A salvage pickup has another lying there once
  `PlayerConfig.respawn` (24 sim hours) has passed since it was last taken, or its own `respawn`
  in `PlayerConfig.salvage`. So the tunnels keep paying, at the economy's prices, for someone who
  goes back. A secret stays taken for good.

## Selling

`Trade` sells to the buyer where the player stands: anywhere in one of the economy's `buyers`, the
scrap trader's stall on the metro's platform and the clinic. `buyer()` names it, by its location's
name, with the economy's price for each kind of salvage they carry. The client's `sell` sells one
item by id, or everything the buyer buys, each through the ledger as `salvage`. The stall needs
nobody behind it for now. A keeper adds what else they trade to their place's buyer through
`keepers_of(app)`, as the clinic's doctor (`simile.clinic`) adds the parts of the body they'd buy
and the bionics they'd fit.

## `player_state`

`PlayerSync` sends `player_state`, the player, the meal on offer, the buyer where they stand and
the piles lying at pickups they haven't taken, to every client:

- to each new client after the snapshot and clock, and after the other modules' greetings, since
  it greets from `running`;
- at once after any change but to hunger or a lamp's charge: money, items, a lamp's switch, the
  body, a pile, a pickup taken, or the meal on offer or the buyer as they walk in or out of
  somewhere to eat or sell;
- and for hunger or a lamp's charge alone, once one of them has moved by `step` (0.01) since the
  last one sent, or reached 0 or 1, so a full or flat battery is never shown a step short. That's
  every 2.4 sim minutes of hunger.

Every constant is in `PlayerConfig`.

## The lamp

`Lamp` (`lamp.py`) runs the lamp the player carries, on the sim loop too, and only while a client is
in the game, like hunger:

- **It drains** by `drain` (3) a sim hour while it's on: a full battery lasts twenty minutes. When
  it runs flat it goes off by itself.
- **It charges** by `charge` (60) a sim hour while the player stands on a plug's stand tile (a
  `plug` interactable: at home, the café, the noodle bar and the metro's maintenance alcove), on or
  off, from flat to full in a minute. Plugged in, it doesn't drain.
- **A collapse switches it off,** so it doesn't run down at home while they recover.
- **The client's `lamp`** switches it on or off (`docs/protocol.md`). Switching on a flat one, or
  to how it already is, does nothing. A switch goes out in `player_state` at once, and the charge
  alone at `step`, as above.

Its rates are in `LampConfig`, beside it.
