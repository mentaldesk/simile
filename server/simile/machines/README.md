# simile.machines

Q4: the machines you repair and then use. Its `running` hook makes a `Workshop` from `player_of(app)`
and adds every machine to the snapshot. `machine_changed` goes out when one is repaired, and the
parts it used up reach the client in the next `player_state`, on the sim loop.

A machine's `id` is its interactable's, on the maker space's map. Each `Machine` is built afresh from
`Player.repaired`, which is all that's saved, so this module stays the source of its parts and offers.

| Machine | Where | What repairing it uses up |
|---|---|---|
| `printer_3d` | Maker space, ground floor (9) | 1 metal sheet, 1 linear actuator, 2 copper wire |
| `recycler` | Maker space, ground floor (1) | 1 Apex control board (`apex_board`), 2 old battery |

`Workshop.repair` works only while the player stands on the machine's stand tile, with every part,
on a machine that's still broken. Otherwise nothing changes.

## Adding a machine's offers

Add a file beside this one with a `register` function. `register_offers` calls it at startup, so you
edit nothing else:

```python
from simile.machines.workshop import Offer, Workshop
from simile.schema import Player, Product


def make(player: Player) -> bool:
    """Takes what it uses and gives what comes out, or returns False and changes nothing."""
    ...


def register(workshop: Workshop) -> None:
    workshop.offer("printer_3d", Offer(Product(item=ROUNDS, uses="plastic", cost=2), make))
```

A broken machine lists none of them. `Workshop.make` runs the one a client asks for, while the
machine works and the player stands at it. The next `player_state` shows what changed.

The client's panel is `client/src/ui/machine-panel.ts`. For `uses: "scrap"` it shows all the
`salvage` they carry by weight, so an offer on scrap should take the same items.
