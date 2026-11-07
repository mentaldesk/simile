# simile.machines

Q4: the machines you repair and then use. Its `running` hook makes a `Workshop` from `player_of(app)`
and adds every machine to the snapshot, subscribes `repair` and `make`, and ticks on the sim loop,
sending `machine_changed` for each machine that's changed. What a `repair` or a `make` used up
reaches the client in the next `player_state`.

A machine's `id` is its interactable's, on the maker space's map. Each `Machine` is built afresh from
`Player.repaired`, which is all that's saved, so this module stays the source of its parts and offers.

| Machine | Where | What repairing it uses up |
|---|---|---|
| `printer_3d` | Maker space, ground floor (9) | 1 metal sheet, 1 linear actuator, 2 copper wire |
| `recycler` | Maker space, ground floor (1) | 1 Apex control board (`apex_board`), 2 old battery |

`Workshop.repair` works only while the player stands on the machine's stand tile, with every part,
on a machine that's still broken. Otherwise nothing changes.

## What the printer makes

`printer.py`. Plastic is `plastic(amount)` in `materials.py`, 0.5 kg each.

| Offer | `id` | Weighs | Takes |
|---|---|---|---|
| Plastic pistol: holds 6, none loaded, new | `plastic_pistol` | 0.5 kg | 6 plastic |
| 6 loose rounds, which join any carried | `plastic_rounds` | 0.02 kg each | 2 plastic |

A pistol's 30 rounds of wear are `simile.combat`'s. Aris's spool on the bench holds 8 plastic, one of
each. It's `maker_space_spool` rather than one of the bench's finds, so a save that's already
searched the bench can still find it.

## What the recycler makes

`recycler.py`. Both offers list only what the player carries now, and each is `uses: "scrap"`, so the
panel shows the item and `cost` in kilos as the server sends them.

| Offer | `id` | Takes | Makes |
|---|---|---|---|
| Plastic | `plastic` | All their scrap: salvage no recipe or repair uses, and not copper pipe | 1 plastic a kilo |
| Copper wire | `copper_wire` | All their copper pipe, 3 kg each | 2 wire a pipe, the same weight |

A press for wire takes every pipe they carry, as a press for plastic takes all their scrap, so the
row says what it'll make of them and goes once they're used. Wire doesn't stack, so the row's `item`
is one lot, `Copper wire ×6` weighing 9 kg, and they get that many single wires, which repairs and
recipes count one by one. Pipes lie in the sewers (`content/street/README.md`) and come back.

## Adding a machine's offers

Add a file beside this one with an `offers` function. `register_offers` calls it at startup, so you
edit nothing else:

```python
from simile.machines.workshop import Offer, Workshop
from simile.schema import Player, Product


def make(player: Player) -> bool:
    """Takes what it uses and gives what comes out, or returns False and changes nothing."""
    ...


def offers(workshop: Workshop) -> None:
    workshop.offer("printer_3d", Offer(Product(item=ROUNDS, uses="plastic", cost=2), make))
```

A broken machine lists none of them. `Workshop.make` runs the one a client asks for, while the
machine works and the player stands at it. The next `player_state` shows what changed. Your `make`
has to refuse what wouldn't fit under their carry limit: the panel says why, and sends nothing.

An offer that depends on what they carry gives a function of the player as its `product`. It returns
what a press would make now, or None to list nothing, and the client hears of each change. The
client can't tell what counts as scrap, so for `uses: "scrap"` the panel shows the product as the
server sends it, with `item.amount` what a press makes and `cost` the kilos it takes. A working
recycler listing nothing says it's carrying no scrap it can use.

The client's panel is `client/src/ui/machine-panel.ts`.
