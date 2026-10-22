# simile.player

S5: the player gets hungry. The player's state is `player_of(app)` (`simile.persistence`), saved
with the world. This module changes it at runtime and tells the client: its `running` hook makes a
`Hunger` and a `PlayerSync` and ticks both on the sim loop.

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
    its keeper is in and their batch lasts. The player pays the keeper through the ledger as from
    `OUTSIDE`, since the ledger keeps residents' money and the player isn't one, and the keeper
    pays the supplies as for any sale. A noodle-bar meal comes out of the batch.
  - **Food they carry** relieves `food` (0.4) an item.
  - `meal()` is the meal on offer where they stand, which goes to the client in `player_state` so
    its hint can offer it. Ordering a drink at the café's counter is unchanged and free.
- **Collapsing.** At 1 they collapse. Everything they carry but the lamp is left in a `Pile` where
  they fell, on the ground below if they were mid-air or partway up stairs or a ladder, at the end
  of `Player.left`. They wake at home, the entry of `home`, with hunger `waking` (0.75), and the
  client gets `player_collapsed` to put them there. The lamp and their money stay with them, so
  they can see to go back for the rest.
- **Picking up.** The client's `pick_up` takes from the nearest pile they left within `reach` (1.5
  tiles) on the map they're on, each item that still fits under their carry limit, in order. Any
  that don't fit stay in the pile.

Home is `PlayerConfig.home`, the maker space: the village has no house for the player, and every
house is someone's. Aris's workshop is the place the story makes theirs until one is added.

## `player_state`

`PlayerSync` sends `player_state`, the player and the meal on offer, to every client:

- to each new client after the snapshot and clock, and after the other modules' greetings, since
  it greets from `running`;
- at once after any change but to hunger or a lamp's charge: money, items, a lamp's switch, the
  body, a pile, or the meal on offer as they walk in or out of somewhere to eat;
- and for hunger or a lamp's charge alone, once one of them has moved by `step` (0.01) since the
  last one sent. That's every 2.4 sim minutes of hunger.

Every constant is in `PlayerConfig`.
