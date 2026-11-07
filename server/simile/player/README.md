# simile.player

S5: the player gets hungry. S6: salvage, and selling it. The player's state is `player_of(app)`
(`simile.persistence`), saved with the world. This module changes it at runtime and tells the
client: its `running` hook joins the player to the economy, makes a `Hunger`, a `Power`, a `Health`,
`Pickups`, a `Trade` and a `PlayerSync`, and ticks `Hunger`, `Power`, `Health` and
`PlayerSync` on the sim loop.

## Hunger

- **It rises** by `rise` (0.25) a sim hour, from fed (0) to starving (1) in four hours, but only
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
  - `shut()` is the shop where they stand while it sells meals but isn't serving them, for the
    hint to say why and when it opens. It's `sold_out` while its keeper is in but the batch has
    gone, otherwise `closed` (off shift, or past the café's last orders). It opens at the next
    start after now of its keeper's shifts (`hours.py`), so while a keeper is late it's their next
    shift, and never while nobody works there.
- **Starving.** At 1 hunger stops rising, and every `StarvingConfig.every` (0.2) sim hours while
  someone's playing and they're awake it takes `damage` (0.1) of their health, `pang` wired to
  `Health.hurt` with `cause` `hunger`. No health comes back and no rest starts in the daytime while
  it lasts. Eating anything stops it. From full health it kills in ten pangs, two sim hours, so six
  sim hours from fed.
- **Once a power cell is in** their stomach, hunger is 0 for good and nothing is on offer to eat:
  `meal()` is none and `eat` does nothing. They run on power instead.

Home is `PlayerConfig.home`, the maker space: the village has no house for the player, and every
house is someone's. Aris's workshop is the place the story makes theirs until one is added.

## Death

`Death` (`corpses.py`) is what happens when health or a power cell runs out, whichever way, with the
`Vital` that ran out as `cause`:

- **The corpse.** A new `Corpse` goes at the end of `Player.corpses`, assigned as a new list so its
  validator checks the id: `next_corpse` gives an id none of the saved ones has, so a reload can't
  reuse one. It holds their money, through the ledger as `dropped`, everything they carried but the
  lamp, and every bionic fitted. It lies on the tile they fell on or the ground below it, or where
  they wake if the server doesn't yet know where they are, as a new body can't keep the old one's
  bionics. It stays whatever it holds, and a second death leaves a second.
- **The lamp** stays with them, switched off, as stage 2's collapse had it, so they can see to go
  back. Everything else they carried is on the corpse.
- **The new body.** `Body()`, whole and organic, so every part can be sold again: the clinic reads
  what it would buy from the body alone, so the kidney sells again. Every effect clears, power is
  full, and hunger is at most `PlayerConfig.waking` (0.75), so they never wake starving.
- **Waking.** In their bed at home, or at its entry without one, with `HealthConfig.waking` (0.25)
  health, resting at once, and whole again in a couple of real seconds. The client gets
  `player_died` to put them there.
- **What stays theirs** isn't their body: their mind, with the recipes they've sold still sold, the
  stash, what buyers keep for them to buy back (`sales`), what they've searched, taken and
  `repaired`, and everything in `left`: a destroyed bot's haul, what of a pickup didn't fit, and what
  they left when they collapsed in a save from before death.

## Salvaging your own body

`Salvage` (`corpses.py`, Q11) is one more claim on `pick_up` (`claimers_of(app)`), made by
`simile.clinic`'s `running` hook, since the clinic's recipes name each bionic.

- **Which corpse.** The nearest within `reach` (1.5 tiles) that they can take something from, the
  oldest of those on a tie, so of two on one tile, which draw as one, the older goes first and the
  next E takes the newer.
- **What comes out.** Its money, through the ledger as `recovered`, then each of its items and then
  each of its bionics, in order, that fits under their carry limit, a stack whole and joining any
  of its `id` they carry. A bionic comes out as a `bionic` item with its grade, named by its recipe,
  weighing what `BIONIC_WEIGHTS` says: half a kilo for the datajack or the eye, up to 8 kg for the
  third legs. A full set is more than a new body carries, so it can take two trips.
- **What doesn't fit** stays on the corpse.
- **An emptied corpse stays,** as every corpse does whatever it holds, picture and all, but E no
  longer offers anything there. The doctor refits what they took (`simile.clinic`'s *Refitting*).

## Power

`Power` (`power.py`, P7) runs the power cell once one is fitted, a `power_cell` grade in place of
the stomach, while a client is in the game, like hunger. Without one, `Player.power` stays full.

- **It drains** by `drain` (0.2) a sim hour, and `per_bionic` (0.1) more for each other bionic
  fitted: five hours on the cell alone, two with the datajack, the legs and the feet.
- **It charges** at a plug as fast as the lamp, from the same `Lamp.charging`: flat to full in
  about three real seconds. Plugged in, it doesn't drain.
- **Running flat** kills them, with `cause` `power`. The new body has no cell, so `power` is full
  again, and it stays full until another is fitted.
- **A cell runs a limited number of bionics** besides itself, by grade, in `runs`: 3 for the
  first cell, 4 for the second and 5 for the third. `runs(body, bionic)` says whether the cell
  would still run everything once `bionic` is fitted, so the clinic fits nothing past it. A higher
  grade of a line in place of a lower one takes no more of the cell.

Its constants are in `PowerConfig`, beside it.

## Health and ailments

`Health` (`health.py`, P9) runs the player's health and their effects, while a client is in the
game, like hunger. It's `health_of(app)` once the `running` hook has made it, for P10's creatures
to hurt and bite the player: they look it up when they do, not at startup.

- **Damage.** `hurt(damage, cause)` takes that much of their health. At none they die of `cause`:
  `hunger` from a pang of starving, and `health` from anything else, even while they're starving.
  See *Death*.
- **Healing.** It comes back by `heal` (0.1) a sim hour, from none to full in ten hours, and
  `heal_at_home` (0.5) at home, in two, standing on their bed too. Their beds are the cells the
  `bed` furniture covers on their home's floor maps (`beds_in`), and `player_state`'s `bed` is the
  one where they stand. The clinic patches them up for money (`simile.clinic`).
- **Resting.** The client's `rest` lies them down in that bed, unless they're at full health or
  infected in the daytime. Once they've lain down, `lie_down` (0.8) real seconds later, it comes back as fast as
  a plug charges the lamp: from none to full in `rest` (3) real seconds, whatever the sim's speed.
  They rest until they're full, move off the bed, an infection sets in or they start starving, they die or they get
  up with `rest`, and `player_state`'s `resting` says so as soon as it changes. Getting back on
  the bed doesn't lie them down again. Waking there after dying, they rest at once, with no
  `lie_down`.
- **Sleeping until morning** (`sleep.py`, P79). At night, from `night_starts` (21:00, the
  earliest bedtime any resident can have, as the client's `NIGHT.from`) until `night_ends`
  (06:00), a rest is accepted at full health or infected too, and goes on until `morning` (07:00)
  rather than ending at full health or when an infection sets in. Once they've lain down, `Sleep`
  runs the clock at `speed` (3600x, an hour a real second) with `clock.skip`, so 02:45 to 07:00
  takes about four real seconds. Health still comes back, unless they're infected or starving, and
  hunger and power hold for the whole rest. At 07:00 the clock goes back to its speed and they get up. Moving
  off the bed, getting up, dying or the client leaving ends it early, and the clock goes back
  at once. Waking in bed after dying at night doesn't sleep until morning.
- **A rat bite.** `bite(damage)` takes `damage` health (a rat's is 0.12, `simile.creatures`)
  and gives them a `rat_bite` effect of `bitten` (0.2) strength, or makes the one they have that
  much stronger, up to 1, keeping `since` from the first. A bite fades by 0.25 a sim hour, so a single one is gone in under an hour. One
  still there `infects` (2) sim hours after `since` turns into an `infection` of the same strength,
  as a handful of bites at once does.
- **An infection** lasts until the clinic treats it (`fades` null). While infected no health comes
  back, even at home, and it takes `infection` (0.02) a sim hour at full strength.
- **Fading.** Each effect loses `fades` of its strength a sim hour, and is gone at 0. Its rate is
  its kind's in `fades`, and `one_kidney` (half) of it with a kidney sold, so a sold kidney slows
  what they have already. Two bites close together fade before they turn on two kidneys, and turn
  on one. Radiation fades by 0.05 an hour, for the deeper sewers.
- **Dying** clears every effect, since they were the old body's.

Its constants are in `HealthConfig`, beside it.

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
  fits under their carry limit, in order, a stack whole and joining any of its `id` they carry.
  Money weighs nothing, and from a pickup goes through the ledger as `found`. Money they left when they collapsed, in an older save, went into the ledger as `dropped`, and
  comes back as `recovered`. Taking from a pickup records when, by its id, in `Player.taken`,
  which is saved, and whatever of it didn't fit becomes a pile of theirs at the end of `left`. Any
  that don't fit of one of theirs stay in it.
- **One thing per press.** Other modules add what else `pick_up` can take to `claimers_of(app)`,
  such as S13's clues, each a `Claim` with its distance from the player. `pick_up` takes the
  nearest claim if it's nearer than any pile in reach, and the pile otherwise, a tie included.
  Never both.
- **The jacks** (`machines.py`, S8) are the machines only the datajack works: the metro's dead
  terminal and its lift, and the sewers' maintenance hatch (S9). With the datajack fitted, standing
  on the stand tile of a jack that holds a fact (`found_in`) is a claim on `pick_up` that writes it
  to the journal, as a clue does, and sends `journal`. The terminal holds the disappearance's
  `lift_log` and the hatch its `hatch_log`; the lift holds none, so a pile
  there is still picked up. Without the datajack nothing claims. The world ignores a
  `player_move` into the sewers from another map until `Player.lift_open`, which having had the
  datajack or left a trace down there sets for good, so a new body can ride it.
- **Salvage comes back; secrets don't.** A salvage pickup has another lying there once
  `PlayerConfig.respawn` (24 sim hours) has passed since it was last taken, or its own `respawn`
  in `PlayerConfig.salvage`, as the depot's parts for a new power cell and legs have
  (`REBUILD_RESPAWN`, 48). So the tunnels keep paying, at the economy's prices, for someone who
  goes back. A secret stays taken for good.

## Finds

`Finds` (`finds.py`, P6) is searching and learning recipes. Where each find is, and what it holds,
is `content/street/README.md`'s *Finds*.

- **Searching** is one more claim on `pick_up` (`claimers_of(app)`), ahead of any pile or clue: a
  `searchable` whose stand tile the player is on, or with the datajack a `jack` that holds `items`
  or `money` or `teaches` a recipe, that isn't in `Player.searched`. They learn the recipe it
  teaches, take its money, paid through the economy's ledger as `found`, and what fits of its
  items, and what doesn't is a new pile of theirs where they stand, at the end of `left`. It's then in `searched`, held nothing or not. A jack holding neither, such as the dead
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
name, with the economy's price for each kind of salvage and part they carry. The client's `sell`
sells one item by id, or everything the buyer buys, each through the ledger as `salvage`. The stall
needs nobody behind it for now. A keeper adds what else they trade to their place's buyer through
`keepers_of(app)`, as the clinic's doctor (`simile.clinic`) adds the parts of the body they'd buy
and the bionics they'd fit.

**Buying back.** A buyer keeps each part (`kind` `part`) it buys, and the salvage in the economy's
`kept`, the sewers' that recipes use up, as a `Sale` at the end of `Player.sales`, saved with the
player, so selling one never leaves them stuck. Other salvage isn't kept: it lies about again.
`buyer()`'s `stock` is what it keeps of theirs, at the economy's `buy_back` (2×) what it paid,
cheapest first, and only where they sold it. The client's `buy` buys back the first of an id in it,
the cheapest, through the ledger as a `purchase` to `OUTSIDE`, if they can pay and it fits under
their carry limit.

**The lamp.** The scrap trader buys the lamp too, at the economy's `lamp` price, and keeps it like a
part: switched off, with the charge it had. Selling everything leaves the lamp, which sells only by
id. Without one the player sees by the infrared eye, if fitted, or not at all, and a plug still
charges their power cell.

## `player_state`

`PlayerSync` sends `player_state`, the player, each recipe they know in full, the meal on offer
or the shop that's shut, the buyer where they stand and the piles lying at pickups they haven't
taken, to every client. The recipes come from `recipes_of(app)`, which modules such as the clinic
fill with theirs. It's sent:

- to each new client after the snapshot and clock, and after the other modules' greetings, since
  it greets from `running`;
- at once after any change but to hunger, power, health, an effect's strength or a lamp's charge:
  money, items, a lamp's switch, the body, an effect gained or gone, a pile, a pickup taken, or the
  meal on offer, the shop that's shut or the buyer as they walk in or out of somewhere to eat or
  sell, or as a shop they're in starts or stops serving, or their bed where they stand or their
  resting in it;
- and for hunger, power, health, an effect's strength or a lamp's charge alone, once one of them
  has moved by `step` (0.01)
  since the last one sent, or reached 0 or 1, so a full or flat battery is never shown a step
  short. That's every 2.4 sim minutes of hunger.

Every constant is in `PlayerConfig`.

## The lamp

`Lamp` (`lamp.py`) runs the lamp the player carries, if they carry one, on the sim loop too, and only while a client is
in the game, like hunger:

- **It drains** while it's on: a full battery lasts `light` (98) real seconds whatever the sim's
  speed, so light is scarce. That just covers the longest run between plugs on the metro and in
  the sewers at a walk (`simile.street.charge`, content/street/README.md's *Light*). When it runs
  flat it goes off by itself.
- **It charges** while the player stands on a plug's stand tile (a `plug` interactable: at home,
  the café, the noodle bar, the metro's maintenance alcove and the sewers' junction boxes), on or
  off, from flat to full in `charge` (3) real seconds whatever the sim's speed. Getting to a plug
  is the game, not waiting at one. Plugged in, it doesn't drain.
- **A death switches it off,** and it stays with them rather than on the corpse, so they can see to
  go back.
- **The client's `lamp`** switches it on or off (`docs/protocol.md`). Switching on a flat one, or
  to how it already is, does nothing. A switch goes out in `player_state` at once, and the charge
  alone at `step`, as above.

Its rates are in `LampConfig`, beside it.
