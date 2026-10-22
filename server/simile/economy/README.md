# simile.economy

E3: the village's money. Every resident has some, and every movement of it goes through a ledger.
E4: what there is to eat, which shops are staffed, their batches and every home's fridge.
S6: the player's money goes through the ledger too, and what salvage sells for.
`economy_of(app)` returns the server's `Economy`, which the lifespan ticks on the sim loop and plugs
into B1's `money`, `price`, `earnings` and `supply` hooks.

## Where the money goes

Money moves between residents, the player (`PLAYER`) and `OUTSIDE`, the world beyond the village:

| | What | When |
|---|---|---|
| In | Wages, for work done for people outside the village | At least every `pay_every` (1) hour at work, and when they stop |
| In | Pensions | A seventh of the week's `amount` every midnight |
| Out | Rent | `rent` (30) every midnight, for everyone |
| Out | Groceries | `groceries` (2.5) a meal, to fill the fridge when it runs low |
| Out | Supplies | A shop's `supplies` share of whatever it takes, paid by its keeper |
| Between residents | Paying at a shop | A meal at the noodle bar or the Daily Grind when they start eating. A drink whenever the café serves them (its `Served` event), and at the noodle bar when they come in while it's staffed, at most once every 90 minutes there |
| Between residents | Loans and repaying them | When B3 finds one in a conversation B2 set up for it (E6) |
| In, from the player | Paying at a shop | A meal at the noodle bar or the Daily Grind (S5) |
| To the player | Salvage (`salvage`) | When they sell it to a buyer (S6) |
| To the player | Money they find (`found`) | When they pick up a secret's cash (S6) |

A shop is run by whoever works there on `takings`: Mirela at the Daily Grind and Odalys at the noodle
bar. They take what customers pay and pay the supplies out of it, so they earn their takings less
their supplies, not a wage. Paying at a shop nobody runs goes outside the village. Prices are in
`EconomyConfig.shops`: the noodle bar's meal is 10 and its drink 3, with 30% of its takings going
on supplies, and the café's drink is 3 and its meal 5, with 60% on supplies.

Rent is paid even by someone who can't cover it, so money can go below nothing: see *Keeping it
bounded*.

`loans.transfer(economy, payer, payee, amount, kind)` hands money from one resident to another,
for loans (`loan`) and repaying them (`repayment`). Unlike rent, it only moves money the payer
holds: anything more, nothing or less, or a payer or payee who isn't a resident, and it moves
nothing and returns False. B3 decides when and how much: see *Loans* in its README.

The `Ledger` keeps every `Entry` (when, kind, amount, payer, payee and the shop) from the opening
balances on, so money in less money out is always the change in what residents hold (`gap` is 0).
I3 saves each entry as it's made, and D1's report shows where the money went during a run.

## The player

The player isn't a resident, so their money isn't in `money`, B1's hooks or what residents hold:
to the residents' books they're outside the village, and what they pay a keeper comes in. But every
movement of their money is in the ledger, so `ledger.net(PLAYER)` is always what they've gained
since it opened. Their money is `Player.money` (`simile.player`), which joins the economy as
`Economy.player` once the server is running, and `pay` moves it for `PLAYER`. Unlike a resident's,
it never goes below nothing, so their side checks they can pay first.

- **Meals.** `buy(PLAYER, shop, price)`, as for a resident: the keeper takes it and pays the
  supplies.
- **Salvage.** `EconomyConfig.salvage` prices each kind by item id, and the `buyers`, the scrap
  trader's stall (`scrap_stall`) and the clinic, pay it. `offer(place, items)` is what the buyer at
  a place pays for one of each of the items it buys, and `sell(place, item)` pays them for one, as
  `salvage` from `OUTSIDE`. Neither buyer is a resident.
- **Money they find.** `find(amount, pickup)`, as `found` from `OUTSIDE`.

| Salvage | Price |
|---|--:|
| Copper wire | 6 |
| Scrap steel | 5 |
| Circuit board | 8 |
| Brass valve | 7 |
| Signal relay | 6 |
| Servo motor | 18 |

The prices are facts of the sim: whoever buys only voices them.

## Work

The economy watches who's working: someone at their workplace for work, or kept there by it, as the
café keeps its barista at the till (B1's `working`). A wage is paid for the hours they're there,
including any overtime. Each shift that starts while it's watching becomes a `Turn`: when they first
got to work, how long they worked during it and straight after, and so whether they were on time,
`late` (more than 5 minutes) or skipped it.

## Stock and staffing

- **Staffed.** A shop is staffed from when its keeper arrives for a shift until the shift ends,
  through their talks and breaks, and for as long as they're still working after it. It serves
  only then, so if the cook skips a shift the noodle bar is shut, and a late cook opens late. The
  café's barista is at work while the café holds them at the till (see `simile.cafe`).
- **Batches.** The noodle bar's keeper cooks a `batch` (6 meals) on arriving for each shift. Each
  meal started there takes one. Once it sells out, the bar feeds nobody for the rest of the
  shift, and what's left when it shuts goes off. Batches cost nothing extra: supplies are still a
  share of what it takes. The Daily Grind has no batches.
- **Fridges.** Every home's fridge holds up to `fridge` (8) meals, and each meal at home takes one.
  Someone at home and awake with `low` (2) or fewer left orders groceries to fill it, paid through
  the ledger, and it's filled there and then. An empty fridge feeds nobody, so someone hungry
  and away from home eats out instead. A fridge nothing is known about starts between `low` and
  full, the same for a home every time, so households don't all order on the same day.
- **Relief follows from stock.** B1's `supply` hook says 0 for hunger at a shop that's shut or
  sold out, and at a home with an empty fridge, so they score nothing for hunger and feed nobody,
  with no special case. A meal already started is finished.
- **Saved.** I3 saves the fridges and each shop's latest batch with the money. A save from before
  E4 stocks the fridges as at the start, and the noodle bar cooks a fresh batch when its keeper
  next arrives.

## For B1

| Hook | |
|---|---|
| `money(npc)` | What they hold now |
| `price(npc, goal)` | Groceries for a meal at home while the fridge has one. At a shop that's staffed its drink, unless they had one there lately, plus its meal if they're hungry enough to eat and it's serving (B1's `supply` for hunger). A keeper at their own shop pays only the supplies for a meal |
| `earnings(npc, goal)` | What an hour at work pays: their wage, or for a shopkeeper `takings` (10), what an hour running the shop is reckoned to bring in |
| `supply(goal, need)` | For hunger: 1 at a shop that's staffed and hasn't sold out, and at home while the fridge has a meal, otherwise 0. 1 for every other need and place |

B1 prices all of these through its `finances` need: see its README.

## Keeping it bounded

Each resident's pay is set so a usual week covers rent and a usual week's food. The rest follows
from B1: above their savings target a price barely registers, so they spend freely, and below it
prices start to hurt, so they eat at home and skip the coffee. Someone short skips fewer shifts
and is more likely to stay on after one. So money drifts towards where spending meets income
rather than running away. `simile behaviour simulate` reports each resident's money every 12 sim
hours, every shift, and the ledger.

A shopkeeper earns only while their shop is staffed. The noodle bar sells two or three meals and
four or five drinks a shift, which leaves Odalys short of her rent and spending, so she runs down,
faster in weeks she skips, and levels off as being short makes her skip less and spend less. Over a
fortnight Kofi, who skips and spends freely, can dip below nothing, as he could before E4.

Every constant is in `EconomyConfig`.
