# simile.economy

E3: the village's money. Every resident has some, and every movement of it goes through a ledger.
`economy_of(app)` returns the server's `Economy`, which the lifespan ticks on the sim loop and plugs
into B1's `money`, `price` and `earnings` hooks.

## Where the money goes

Money moves between residents and `OUTSIDE`, the world beyond the village:

| | What | When |
|---|---|---|
| In | Wages, for work done for people outside the village | At least every `pay_every` (1) hour at work, and when they stop |
| In | Pensions | A seventh of the week's `amount` every midnight |
| Out | Rent | `rent` (30) every midnight, for everyone |
| Out | Groceries | `groceries` (2.5) when they start a meal at home |
| Out | Supplies | A shop's `supplies` share of whatever it takes, paid by its keeper |
| Between residents | Paying at a shop | A meal at the noodle bar or the Daily Grind when they start eating, and a drink whenever the café serves them (its `Served` event) |
| Between residents | Loans and repaying them | When B3 finds one in a conversation B2 set up for it (E6) |

A shop is run by whoever works there on `takings`: Mirela at the Daily Grind and Odalys at the noodle
bar. They take what customers pay and pay the supplies out of it, so they earn their takings less
their supplies, not a wage. Paying at a shop nobody runs goes outside the village. Prices are in
`EconomyConfig.shops`: the noodle bar's meal is 8, the café's drink 3 and its meal 5.

Rent is paid even by someone who can't cover it, so money can go below nothing. Nobody does in
B1's fast-forward: see *Keeping it bounded*.

`loans.transfer(economy, payer, payee, amount, kind)` hands money from one resident to another,
for loans (`loan`) and repaying them (`repayment`). Unlike rent, it only moves money the payer
holds: anything more, nothing or less, or a payer or payee who isn't a resident, and it moves
nothing and returns False. B3 decides when and how much: see *Loans* in its README.

The `Ledger` keeps every `Entry` (when, kind, amount, payer, payee and the shop) from the opening
balances on, so money in less money out is always the change in what residents hold (`gap` is 0).
I3 saves each entry as it's made, and D1's report shows where the money went during a run.

## Work

The economy watches who's working: someone at their workplace for work, or kept there by it, as the
café keeps its barista at the till (B1's `working`). A wage is paid for the hours they're there,
including any overtime. Each shift that starts while it's watching becomes a `Turn`: when they first
got to work, how long they worked during it and straight after, and so whether they were on time,
`late` (more than 5 minutes) or skipped it.

## For B1

| Hook | |
|---|---|
| `money(npc)` | What they hold now |
| `price(npc, goal)` | Groceries for a meal at home, and at a shop that's serving (B1's `supply` for hunger) its drink, plus its meal if they're hungry enough to eat |
| `earnings(npc, goal)` | What an hour at work pays: their wage, or for a shopkeeper `takings` (10), what an hour running the shop is reckoned to bring in |

B1 prices all of these through its `finances` need: see its README.

## Keeping it bounded

Each resident's pay is set so a usual week covers rent and a usual week's food. The rest follows
from B1: above their savings target a price barely registers, so they spend freely, and below it
prices start to hurt, so they eat at home and skip the coffee. Someone short skips fewer shifts
and is more likely to stay on after one. So money drifts towards where spending meets income
rather than running away. `simile behaviour simulate` reports each resident's money every 12 sim
hours, every shift, and the ledger.

Every constant is in `EconomyConfig`.
