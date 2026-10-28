# simile.creatures

The tunnels' creatures (P10): the engine every kind runs on, ticked on the sim loop and sent to the
client, which draws them from their figures (`client/src/side/creatures/`). The figures themselves
are painted here too, by `build.py` and `cli.py` ([`content/creatures/`](../../../content/creatures/README.md)).

## Defining a kind

A `Kind` (`kind.py`) is what every creature of a kind shares. Its `id` is the figure it's drawn as
(`rat`, `bot`, `dog` or `bat`), and the rest are its numbers, in tiles, sim seconds and tiles a sim
second:

| Field | Default | |
|---|--:|---|
| `ways` | none | Its ways of moving, below, first first. |
| `speed` | 1 | Its own pace; each way can go `pace` times it. The player walks 2.6 tiles a second and runs 5.2 on their own legs. |
| `think` | 0.25 | How often it chooses where to go. |
| `flies` | no | Through any open cell, rather than along floors. |
| `climbs` | yes | Up and down ladders. Every walking kind takes stairs. |
| `doors` | yes | Onto a door's tile, a link's end on its map. No creature takes a link to another map. |
| `drops` | yes | Off a ledge or through a hole to the floor below. |
| `reach` | 0.7 | How near the player it hurts them. |
| `bites` | no | Hurts with `health_of(app).bite()`, which can turn infected, rather than `hurt(damage)`. |
| `damage` | 0.05 | Health each attack takes, if it doesn't bite. |
| `windup` | 0.3 | How long it shows its attack before it lands. |
| `lunges` | no | Keeps after the player while its attack winds up, so running doesn't get away. |
| `rest` | 1 | How long after an attack before the next. |
| `stomped` | no | Goes down when the player lands on it (below). |

The tunnels' kinds are in `kinds.py` (below).

## The kinds

`kinds.py` has the tunnels' kinds, and `KINDS` each one a map can place, with its `respawn`.

| | Rat (P13) | Recycler bot (P13) | Wild dog (P14) | Bat (P15) |
|---|---|---|---|---|
| Ways | `Scurry`, `DrawnTo(food, within=8, pace=1.4, attacks)`, `Patrol` | `Chase(sight=5, pace=1.5, memory=3, when=fitted)`, `Collect(within=14, pace=0.2)`, `Patrol(pause=3)` | `Chase(sight=10, pace=4, memory=3)`, `Patrol(pause=2)` | `Chase(sight=8, pace=4, memory=2, when=lamp_on)`, `Roost` |
| Speed | 2, and 2.8 after food: it catches a walking player, not a running one | 1.2, 1.8 chasing: slower than a walk, and 0.24 drifting to salvage | 4, and 16 chasing: faster than the best legs (13). It thinks every 0.1 s, so it keeps up | 3, and 12 chasing: faster than any legs but the best (13). It flies, and thinks every 0.15 s |
| Attack | Bites, then scurries home and rests 6 s before the next | `hurt(0.1)` after a 0.6 s windup, then rests 2 s | `hurt(0.1)` from 1.2 tiles after a 0.3 s windup, lunging, then rests 0.9 s | `hurt(0.03)` after a 0.3 s windup, lunging, then rests 2 s, staying on the player |
| Landed on | Goes down, and it's back 120 s later | Never goes down until there are weapons: landing on one is landing in its reach | As the bot | Never: it flies |
| Climbs | No | Yes | No, and takes no door | Flies |

A rat leaves a player who carries no food alone, so a handful of them costs some health only
when the player brings food, and they scatter after each bite. A bot ignores a wholly human
player and chases one with any bionic (`fitted`): in the sewers that's always, since the lift
takes the datajack. Bots are placed to start within `Collect`'s reach of salvage but patrol at
least eight steps from any, so a player who heads straight for it gets there first.

Three dogs keep to their den (`content/street/README.md`), and nothing puts them down or holds
them back. A player on their own legs or the feet is bitten about fifteen times going through and
back, and collapses. On the first legs, running through leaves about a tenth of their health, and
the best legs a quarter or so (`tests/creatures/test_den.py`).

A bat hangs at its roost while the player's lamp is off, however near they are. While it's on, a
bat that sees the lamp, with nothing solid between, flies at the player's chest and keeps
attacking, and goes back to its roost once the lamp's off. Walking across a
room of two roosting bats by lamplight and back costs about a fifth of the player's health, and
running about a twentieth; with the lamp off, nothing. The cave's thirty bats
collapse a player who crosses it by lamplight on any legs, and leave one who crosses in the dark
untouched (`tests/creatures/test_bats.py`).

## Placing them

The maps place them: each map's `creatures` layer (`content/street/README.md`) says where each
starts, its kind, the area it keeps to and the span it patrols. The `running` hook spawns every
one on the maps the world plays (`placing.py`) and removes them when it stops.

`creatures_of(app).spawn(kind, MapTile(...))` puts one in the world, from any module's lifespan,
since `creatures_of` makes the engine on first use. Creatures aren't saved: they're spawned again
each time the server starts. Options:

- `area`, a `TileArea` it never leaves, for a den or a cave.
- `route`, the cells it patrols, or else the floor (or air) `span` (5) cells either side of where it
  starts, as far as it can walk.
- `roost`, where a bat hangs, or else under the ceiling straight above where it starts.
- `respawn`, sim seconds after going down that it's back where it started, or never.
- `id`, or else `<kind>_<n>`.

A walking creature placed in the air stands on the floor under it. Placing one where its kind can't
be, or on a map that isn't side-view, raises `ValueError`.

## Moving

Each creature moves by cells, along its map's grid as its kind allows (`grid.py`): left and right
along a floor, up and down ladders and stairs as `simile.street.moves` has them, and stepping off a
ledge or into a hole to fall to the floor below. A flier goes through any cell that isn't solid,
diagonally only past two open ones. Paths are A\*; with no way to its target, a creature goes to
where it gets nearest and waits there, as a dog under a ladder.

Every `think` (a quarter of a sim second unless its kind says otherwise) each creature asks its
kind's ways, in order, where to go (`ways.py`), and the first with an answer, an `Aim`, decides.
With none, it stands still, `idle`.

| Way | Goes | State |
|---|---|---|
| `Patrol(pause)` | Back and forth along its route, stopping `pause` at each end. | `moving` |
| `Chase(sight, pace, memory, when)` | After the player while it sees them within `sight`, nothing solid between, and `when` holds; then to where it saw them last, for `memory`. Attacks in reach. | `chasing` |
| `FleeLight(radius, lit, within, pace)` | Out of the lamp's light (`radius`, 4.5 tiles, as the client draws it) and, with `lit`, the map's lit stretches, to the nearest dark cell within `within`, or else as far from the lamp as it can. | `fleeing` |
| `DrawnTo(lure, within, pace, attacks)` | Towards `lure` while it's within `within`: `food`, the player while they carry food, or `lamp`, theirs while it's on. Attacks in reach if `attacks`. | `moving`, or `chasing` if it attacks |
| `Roost(when)` | A bat to its roost, to hang there while `when` holds. | `moving`, then `roosting` |
| `Scurry(pace)` | Home after its attack lands, until it's rested. | `fleeing` |
| `Collect(within, pace)` | To the nearest salvage lying within `within` (4) cells' walk, to take it (below). | `moving`, then `attacking` |

A way is anything with `aim(creature, senses)`. `Senses` has the time, the map, and the player and
where the server keeps them, but only while a client is in the game and they're on the creature's
map, with `lamp` and `carries(kind)`, and the `salvage` lying on the map. `lamp_on` is a `when`
for bats, and `fitted` for bots.

## Hurting the player

A creature whose way attacks, in `reach` of the player, starts its attack: `attacking` for `windup`,
facing them. Then, if they're still in reach, it lands, `bite()` or `hurt(damage)` on
`health_of(app)`, looked up as it lands, and it rests for `rest`. A kind that `lunges` keeps
moving after the player while it winds up. A player more than 0.8 tiles above a walking creature
has jumped out of its reach.

The server keeps the player where their last `player_move` put them, up to one throttle interval
(0.2 s) behind the client. The windup is at least that long, so by the time an attack lands the
server has heard where they went after it started: a player who moves away from a rat as it starts
to bite is out of reach when the bite lands, and isn't bitten. A shorter windup would bite players
who had already got away. The windup is in sim seconds and the throttle in real ones, so at
`--speed 2` a 0.3 s windup is only 0.15 real seconds, shorter than the throttle.

## Collecting

A creature whose aim `collects`, standing on the pickup it went to, takes the salvage lying there
after `COLLECTING` (4 s), `attacking` meanwhile. If it's gone before then, picked up by the player
or out of sight as they leave the map, the creature gives up. The `running` hook has the salvage
lying at each map's pickups from `simile.player`'s `Pickups`, and a take records it in
`Player.taken`, as the player's own does: it lies there again on the same clock, it's saved, and the
client stops showing it. Creatures sense salvage only while the player is on their map, so a bot
races them for it rather than clearing it while they're away.

## Landing on one

The player kills a rat by landing on it, as in the classic platformers. Each tick the engine compares
where the server keeps the player with where it kept them the tick before: feet that came down
from above a `stomped` creature's back (`STOMP_TOP`, 0.4 tiles over its floor) to it or below,
within `STOMP_REACH` (0.9 tiles) of it, put it down: `creature_gone`, and it's back after `respawn`
if it has one. Walking into one, jumping up past it or coming down beside it doesn't. The reach is
the player's foot and half a rat, and slack for the rat having moved on since the client drew it.

The client bounces the player off the rat as their feet reach its back, and sends that position at
once (`client/src/side/stomp.ts`), so the server hears the feet come down on it. Landing on a bot or
a dog puts the player in its reach, and it attacks as it would anyway.

## To the client

The snapshot carries every creature, and `creature_moved` each change: at once for a change of
state or facing, and every `SEND` (0.2 sim seconds) while one moves, with where it is mid-step. The
client tweens between them. A walking creature's position is the floor under it, and a bat's the
middle of its cell, or the ceiling above it while it roosts.
