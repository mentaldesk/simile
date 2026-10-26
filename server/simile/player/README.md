# simile.player

S5: the player gets hungry. S6: salvage, and selling it. The player's state is `player_of(app)`
(`simile.persistence`), saved with the world. This module changes it at runtime and tells the
client: its `running` hook joins the player to the economy, makes a `Hunger`, a `Power`, a `Health`,
`Kicks`, `Pickups`, a `Trade` and a `PlayerSync`, and ticks `Hunger`, `Power`, `Health` and
`PlayerSync` on the sim loop.

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
  client gets `player_collapsed` to put them there, with `cause` `hunger`. The lamp and their money
  stay with them, so they can see to go back for the rest.
- **Once a power cell is in** their stomach, hunger is 0 for good and nothing is on offer to eat:
  `meal()` is none and `eat` does nothing. They run on power instead.

Home is `PlayerConfig.home`, the maker space: the village has no house for the player, and every
house is someone's. Aris's workshop is the place the story makes theirs until one is added.

## Power

`Power` (`power.py`, P7) runs the power cell once one is fitted, a `power_cell` grade in place of
the stomach, while a client is in the game, like hunger. Without one, `Player.power` stays full.

- **It drains** by `drain` (0.2) a sim hour, and `per_bionic` (0.1) more for each other bionic
  fitted: five hours on the cell alone, two with the datajack, the legs and the feet.
- **It charges** at a plug as fast as the lamp, from the same `Lamp.charging`: flat to full in
  about three real seconds. Plugged in, it doesn't drain.
- **Running flat** collapses them as hunger does, with `cause` `power`, and they wake at home with
  `waking` (0.25) power.
- **A cell runs a limited number of bionics** besides itself, by grade, in `runs`: 3 for the
  first cell, 4 for the second and 5 for the third. `runs(body, bionic)` says whether the cell
  would still run everything once `bionic` is fitted, so the clinic fits nothing past it. A higher
  grade of a line in place of a lower one takes no more of the cell.

Its constants are in `PowerConfig`, beside it.

## Health and ailments

`Health` (`health.py`, P9) runs the player's health and their effects, while a client is in the
game, like hunger. It's `health_of(app)` once the `running` hook has made it, for P10's creatures
to hurt and bite the player: they look it up when they do, not at startup.

- **Damage.** `hurt(damage)` takes that much of their health. At none they collapse as when they
  starve, with `cause` `health`, and wake at home with `waking` (0.25) health.
- **Healing.** It comes back by `heal` (0.1) a sim hour, from none to full in ten hours, and
  `heal_at_home` (0.5) at home, in two. The clinic patches them up for money (`simile.clinic`).
- **A rat bite.** `bite()` takes `bite` (0.05) health and gives them a `rat_bite` effect of
  `bitten` (0.2) strength, or makes the one they have that much stronger, up to 1, keeping `since`
  from the first. A bite fades by 0.25 a sim hour, so a single one is gone in under an hour. One
  still there `infects` (2) sim hours after `since` turns into an `infection` of the same strength,
  as a handful of bites at once does.
- **An infection** lasts until the clinic treats it (`fades` null). While infected no health comes
  back, even at home, and it takes `infection` (0.02) a sim hour at full strength.
- **Fading.** Each effect loses `fades` of its strength a sim hour, and is gone at 0. Its rate is
  its kind's in `fades`, and `one_kidney` (half) of it with a kidney sold, so a sold kidney slows
  what they have already. Two bites close together fade before they turn on two kidneys, and turn
  on one. Radiation fades by 0.05 an hour, for the deeper sewers.
- **Collapsing** for health keeps their effects: an untreated infection still needs the clinic.

Its constants are in `HealthConfig`, beside it.

## Kicking

`Kicks` (`kick.py`) is the client's `kick`, from where the server keeps the player on a side-view
map, the way the client says they face. A kick is a `Kick`: where, which way, its `strength` (the
legs' `jump_of(body).kick`, 1 on their own legs and 2 to 4 up the bionic legs) and its `reach`
(1.2 tiles). Whatever can be kicked adds a `Kickable` to `kickables_of(app)`, as P10's creatures
will: given the kick, it says what it would hit and how far away, as a `Hit`. The kick lands on
the nearest hit, and only that one. Nothing else is kicked yet.

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
  money and a ration pack in the metro, the 60 on the high ledge only the spring feet reach.
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
  terminal and its lift, and the sewers' maintenance hatch (S9). With the datajack fitted, standing
  on the stand tile of a jack that holds a fact (`found_in`) is a claim on `pick_up` that writes it
  to the journal, as a clue does, and sends `journal`. The terminal holds the incident's
  `lift_log` and the hatch its `hatch_log`; the lift holds none, so a pile
  there is still picked up. Without the datajack nothing claims, and the world ignores a
  `player_move` into the sewers from another map.
- **Salvage comes back; secrets don't.** A salvage pickup has another lying there once
  `PlayerConfig.respawn` (24 sim hours) has passed since it was last taken, or its own `respawn`
  in `PlayerConfig.salvage`. So the tunnels keep paying, at the economy's prices, for someone who
  goes back. A secret stays taken for good.

## Finds

`Finds` (`finds.py`, P6) is searching and learning recipes. Where each find is, and what it holds,
is `content/street/README.md`'s *Finds*.

- **Searching** is one more claim on `pick_up` (`claimers_of(app)`), ahead of any pile or clue: a
  `searchable` whose stand tile the player is on, or with the datajack a `jack` that holds `items`
  or `teaches` a recipe, that isn't in `Player.searched`. They learn the recipe it teaches, take
  what fits of its items, and what doesn't is a new pile of theirs where they stand, at the end of
  `left`. It's then in `searched`, held nothing or not. A jack holding neither, such as the dead
  terminal or the lift, is never searched, so E there finds its clue at once; one with both gives
  what it holds first and its clue on the next E.
- **Learning** adds a recipe to `Player.mind` once, and only one in `recipes_of(app)`, so
  `player_state` can always carry it in full.
- **Being told.** `FindsConfig.told` is the recipe a place's keeper tells them on walking in: the
  doctor the power cell's, at the clinic, since nothing she fits runs without one. `Finds` ticks
  on the sim loop to hear it.

## Selling

`Trade` sells to the buyer where the player stands: anywhere in one of the economy's `buyers`, the
scrap trader's stall on the metro's platform and the clinic. `buyer()` names it, by its location's
name, with the economy's price for each kind of salvage they carry. The client's `sell` sells one
item by id, or everything the buyer buys, each through the ledger as `salvage`. The stall needs
nobody behind it for now. A keeper adds what else they trade to their place's buyer through
`keepers_of(app)`, as the clinic's doctor (`simile.clinic`) adds the parts of the body they'd buy
and the bionics they'd fit.

## `player_state`

`PlayerSync` sends `player_state`, the player, each recipe they know in full, the meal on offer,
the buyer where they stand and the piles lying at pickups they haven't taken, to every client. The
recipes come from `recipes_of(app)`, which modules such as the clinic fill with theirs. It's sent:

- to each new client after the snapshot and clock, and after the other modules' greetings, since
  it greets from `running`;
- at once after any change but to hunger, power, health, an effect's strength or a lamp's charge:
  money, items, a lamp's switch, the body, an effect gained or gone, a pile, a pickup taken, or the
  meal on offer or the buyer as they walk in or out of somewhere to eat or sell;
- and for hunger, power, health, an effect's strength or a lamp's charge alone, once one of them
  has moved by `step` (0.01)
  since the last one sent, or reached 0 or 1, so a full or flat battery is never shown a step
  short. That's every 2.4 sim minutes of hunger.

Every constant is in `PlayerConfig`.

## The lamp

`Lamp` (`lamp.py`) runs the lamp the player carries, on the sim loop too, and only while a client is
in the game, like hunger:

- **It drains** by `drain` (3) a sim hour while it's on: a full battery lasts twenty minutes. When
  it runs flat it goes off by itself.
- **It charges** while the player stands on a plug's stand tile (a `plug` interactable: at home,
  the café, the noodle bar and the metro's maintenance alcove), on or off, from flat to full in
  `charge` (3) real seconds whatever the sim's speed. Getting to a plug is the game, not waiting at
  one. Plugged in, it doesn't drain.
- **A collapse switches it off,** so it doesn't run down at home while they recover.
- **The client's `lamp`** switches it on or off (`docs/protocol.md`). Switching on a flat one, or
  to how it already is, does nothing. A switch goes out in `player_state` at once, and the charge
  alone at `step`, as above.

Its rates are in `LampConfig`, beside it.
