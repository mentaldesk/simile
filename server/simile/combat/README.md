# simile.combat

The player's `fire` and `reload` ([`docs/protocol.md`](../../../docs/protocol.md)). `PlayerSync` sees
what changed in what they carry on its next tick and sends the `player_state`. `simile.creatures`
takes the damage and sends `creature_hit`.

## The shot

A shot starts in the column the player stands in and carries `RANGE` (12) columns the way they face.
It's as tall as their figure, the row their feet are in and the one above, so it hits a rat on their
floor and a bat at their chest. A jump lifts it over a rat. A wall stops it in the row the wall is
in. It ends at the nearest creature in line, or once walls have stopped it in both rows.

A hit takes `DAMAGE` by the weapon's material, since loaded rounds are a plain count:

| | Plastic rounds to kill |
|---|---|
| Rat, bat | 1 |
| Wild dog | 3 |
| Recycler bot | 6 |

Each kind's `health`, in points, is in `simile/creatures/kinds.py`. The engine counts the points lost,
so three thirds come to exactly none.

## Wear

A new weapon's `condition` is 1, and it fires `LASTS` rounds by its material: 30 for plastic.
Condition is counted in rounds rather than by subtracting 1/30, which would leave a little over 0
after thirty and allow a 31st shot. A worn-out weapon neither fires nor reloads, and keeps whatever
it has loaded.
