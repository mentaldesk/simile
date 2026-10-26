# Client–server protocol

The client and the sim server talk over one WebSocket at `/ws`. In development the client connects
to its own origin and Vite proxies `/ws` to the server on port 8000.

- **Text frames** carry one JSON message each, with a `type` field naming the message.
- **Binary frames** go from the server to the client only, and are always an [`audio_chunk`](#audio_chunk).

The server is authoritative, except for the player's position, which the client sends. The server
moves the player only when they collapse ([`player_collapsed`](#player_collapsed)).

The message models are in [`server/simile/protocol/messages.py`](../server/simile/protocol/messages.py),
built on the F2 domain schemas in `server/simile/schema/`. The TypeScript types in
[`client/src/net/protocol.ts`](../client/src/net/protocol.ts) are generated from them.

## Conventions

The village is drawn from the side (#306): a map per street and a map per floor. The isometric
maps it replaced are gone (#315), but some defaults still name their village, `"village"`, and the
interiors' ids; this document says where.

- Field names are `snake_case` on both sides.
- Every field is always present. Optional values are `null`, never missing. The exceptions are a
  position's `map`, an entity's `pose` and `facing`, a line's `flushed`, an article's
  `long_summary`, a wall's `map`, a player's `left`, `taken`, `mind`, `power`, `health`, `effects`,
  `sales` and `searched`, a body's `stomach` and `feet`, a mind's `sold`, a pile's `money`, a
  buyer's `parts`, `fittings`, `recipes`, `stock` and `treatments`, and `player_state`'s `meal`,
  `shut`, `buyer`, `piles` and `recipes`, below.
- Timestamps are sim time: ISO 8601 in UTC, e.g. `"2026-03-14T09:10:03Z"`. UTC is village time.
- A **position** is `{"x": 4.5, "y": 6, "map": "village"}` in tiles, measured like F2's `Tile`:
  `(4, 6)` is standing on tile (4, 6), and fractions are part-way between tiles while walking.
  `map` is the map it's on: `"village"`, or an interior's id, such as `"coffee_shop"`.
  - The server always sends `map`. A client may leave it out of `player_move`, which means the
    village, so clients that predate interiors keep working.
  - So the generated TypeScript has `map?: string`, and the client can keep using `Position` as a
    plain point. Read it as `position.map ?? 'village'`. K5 (#171) may tighten the type.
  - On a side-view map, x runs along the street and y counts rows down from the top. `map` is a
    street's or a floor's id. A tile is about 1.1 m, as on the isometric maps, so distances in
    tiles mean the same in both. A resident stands on a cell with ground under it, or on a
    climbable cell (stairs or a ladder), and fractions are mid-step or mid-climb. The player can
    also be mid-air, jumping or falling (see [`player_move`](#player_move)).
- An entity's **pose** is what it's doing: `"standing"`, `"walking"`, `"sitting"`, `"reading"`,
  `"working"`, `"looking"`, `"climbing"` (on stairs or a ladder) or `"riding"` (in a lift). Its
  **facing** is the way it faces on the map, x east and y south: `"east"`, `"south_east"`,
  `"south"`, `"south_west"`, `"west"`, `"north_west"`, `"north"` or `"north_east"`, in order of
  angle from east round through south. Both are F2 types, `Pose` and
  `Facing` in `server/simile/schema/world.py`, so the world and the sim's events can use them too.
  - On a side-view map, the three eastward facings draw them facing right and the three westward
    ones left. `north` draws their back, looking into the picture (at a mural or a terminal), and
    `south` their front.
  - The server always sends both. Without them an entity is standing, facing south-east. As with
    `map`, the generated TypeScript has them optional: read `entity.pose ?? 'standing'` and
    `entity.facing ?? 'south_east'`.
  - Sitting, reading, working and looking come with #264's spots, which face along the grid:
    `north`, `east`, `south` or `west`.
  - The server doesn't track the player's, so the player's entity is always `standing`, facing
    `south_east`.
- Entity ids are F2 `Id`s. The player is always `"player"`.
- The maps aren't sent: the client bundles the village and its interiors as Tiled maps. F2's
  `Door` and `Interactable` in `server/simile/schema/world.py` describe their doors and the things
  you can use inside, and a `Location` says which map it's on. Interactable ids go over the wire
  only in [`paintings`](#paintings) and the player's `searched`.
  - An `Interactable`'s `kind` is `"counter"`, `"painting"`, `"machine"`, `"plug"`, `"jack"` or
    `"searchable"`. A plug charges the player's lamp, on or off, while they stand on one of its
    `stand` tiles, so the client finds the plugs, and whether the lamp is charging, from the maps.
  - A jack is a machine only the datajack works, such as the metro's dead terminal and its
    maintenance lift. With the datajack fitted (`player_state`'s `body`), E at one sends
    [`pick_up`](#pick_up), which finds the clue it holds, if any. A link ending on one of its
    `stand` tiles, like the lift's down to the sewers, is taken only with the datajack. Without
    one the jack is dead: the client says so, and offers no link from it.
  - A searchable thing is a piece of furniture or a dead appliance, such as the maker space's
    drawers or a dead fridge in the metro, searched once for what it holds. Its `items` are what
    searching it finds, `money` the cash in it, which weighs nothing, and `teaches` the recipe it
    teaches, by the `Bionic` it builds, such as Aris's schematic on her bench for the datajack.
    Any may be empty, a thing with nothing in it. A jack can hold and teach too, such as the
    sewers' security terminal with the infrared eye's recipe, and is searched, with the datajack,
    only while it has `items`, `money` or `teaches`: a jack that holds none, like the metro's dead
    terminal or its lift, is never searched. Each is left out while it's empty, and no other kind
    holds or teaches anything. E at one sends
    [`pick_up`](#pick_up), and the player's `searched` says which they've searched, so the client
    can tell what's left, from the maps.
  - A `Door`'s `kind` is `"door"`, `"stairs"`, `"ladder"` or `"lift"`, and it's left out for a
    door. A door joins a street or the village (`outside`) and a building's ground floor
    (`inside`), or two streets, with `outside` on the street whose id comes first alphabetically:
    `"high_street"` before `"mill_lane"`. Stairs, a ladder or a lift join two floors' maps, with
    `outside` the lower and `inside` the upper. Stairs and ladders within one map aren't doors:
    they're climbable cells on the map.
  - No two links share an end tile. The client finds a link from its end tile, and the server's
    `door_ends` (`server/simile/world/paths.py`) keys links by their end tiles, so it would drop
    one of two that share a tile. A lift serving three or more floors, or two flights of stairs
    meeting on a landing, has a separate end tile on the middle floor for each link. #308's map
    loader rejects a map that breaks this.
  - A `Location`'s `map`, `area` and `entry` are where you arrive. On side-view maps its `floors`
    are its building's other floors, each a `MapArea` (a `TileArea` with a `map`) on a map of its
    own. It's left out when empty.
- A message the server can't parse is logged and ignored. The connection stays open.

## Server → client

### `snapshot`

The whole world. The server sends it first on every connection, including reconnections, and the
client replaces whatever it had.

| Field | Type | |
|---|---|---|
| `time` | timestamp | Sim time now. |
| `map_id` | string | The map the player starts on, e.g. `"village"`, or on side-view maps a street's id. |
| `entities` | `Entity[]` | Every NPC and the player: `id`, `kind` (`"npc"` or `"player"`), `name`, `position`, `pose` and `facing`. Each position has its own `map`. The player's can be mid-air, where a jump or a fall was when the server last heard (see [`player_move`](#player_move)). |
| `conversations` | `Conversation[]` | Conversations still going on, with their lines so far (F2 `Conversation`). |
| `level` | number | Which of the generated levels in `content/street/levels/` this world plays, picked by its seed: the maps in `levels/<level>/`, such as the sewers. The client bundles every level and plays this one's maps. The server always sends it; missing, it's 0. |
| `creatures` | `Creature[]` | Every creature on every map. The server always sends it; missing, there are none. |

A `Creature` is one of the tunnels' dangers, which the sim runs and the client draws and animates.
It has its `id`; its `kind`, named as its figure is in `content/creatures/`: `"rat"`, `"bot"` (a
recycler bot), `"dog"` (a wild dog) or `"bat"`; its `position`, with its `map`; its `facing`, a
`SideFacing`, `"east"` to draw it facing right or `"west"` facing left, as creatures are only on
side-view maps; and its `state`, what it's doing, which picks the pose its figure plays:

| `state` | Pose |
|---|---|
| `"idle"` | `stand`, or for a bat `fly`, on the spot. |
| `"moving"`, `"chasing"`, `"fleeing"` | Its kind's cycle: `walk` for rats and bots, `run` for dogs, `fly` for bats. |
| `"attacking"` | `attack`. |
| `"roosting"` | `roost`, hanging from the ceiling. Only a bat roosts. |
| `"hurt"` | Just kicked: `stand`, or for a bat `fly`. |

A walking kind's position is the ground under it, its figure's anchor, and a bat's is the middle of
it in the air, or the ceiling it hangs from while it roosts. How a creature moves, its health and
what it does on contact stay on the server.

Until the sim has a world of its own, the snapshot comes from F2's fixtures in
`server/tests/fixtures/`: the NPCs at their front doors, the player in the town square, and the one
conversation that hasn't ended. Its `time` is the sim clock's.

### `clock`

`time` (sim time) and `speed` (sim seconds per real second, more than 0). The server sends it
straight after every `snapshot`, when the speed changes, and as each sim minute starts, so the client
can keep its own clock in between: sim time now is about `time` + `speed` × the real seconds since
it arrived.

### `entity_moved`

`entity_id`, `position`, `pose` and `facing`. On its way somewhere an entity is `walking`, facing
the way it's going, so the client can still work the facing out from the direction of travel. When
it settles, say at a seat, an `entity_moved` gives the pose and facing it stays in. That can be at
the position it's already at, so the pose or facing can change on its own.

An entity going through a door arrives as an `entity_moved` onto the other map, and the client
snaps it there rather than walking it. The `entity_moved` before that is the door's tile on the map
it's leaving, a step's time earlier.

On a side-view map:

- An entity on a run of stairs or ladder cells within one map is `climbing`.
- One taking stairs, a ladder or a lift to another floor's map gets an `entity_moved` at the
  link's end on the map it's leaving, `climbing` or `riding`. It holds that for the climb or ride,
  then arrives on the other map as through a door.
- The client finds the link from that end tile, which no other link shares, and plays a climb or
  a ride by its `kind`.

### `creature_moved`

`creature`: a `Creature`, all of it, as in the [`snapshot`](#snapshot). The server sends it as a
creature moves, turns or changes state. One the client doesn't have yet has just appeared, and the
client adds it.

### `creature_gone`

`creature_id`: a creature that's gone from the world, such as a rat kicked to death. The client
removes it.

### `conversation_started`

`conversation`: an F2 `Conversation`, usually with no lines yet.

### `conversation_ended`

`conversation_id`, `ended` (timestamp).

### `line`

`line`: an F2 `Line` (`id`, `conversation_id`, `speaker`, `text`, `timestamp`, and `duration`, the
estimated seconds to say it). `voiced`: whether `audio_chunk` frames will follow for `line.id`.
When it's `false`, show the text for `duration` seconds.

`flushed`: `true` when the client shows a flush on the speaker as they say the line, which the
player sees through the infrared eye. The server sets it exactly when the line is a lie, as the
code decides it, and the player has the eye fitted, so the client draws it as given and never
guesses. It's left out unless it's `true`, so a client that predates it, and every line without a
flush, look as before: read it as `message.flushed ?? false`. A flush the player sees on a line
that tells them something about the incident is also marked in the [`journal`](#journal).

### `npc_state`

`npc_id`, and `state`, an open JSON object for the debug overlay (I2). Each module puts its own keys
in `state`, for example `{"goal": "coffee_shop"}`. The keys aren't part of the contract and can grow
without changing the protocol. The server sends it only for the NPC the client is watching
([`watch_npc`](#watch_npc)).

### `news`

`articles`: the articles at the news terminals, newest first. Each has its `news_id` (the F2
`NewsItem` id), `title`, `source` (the feed's display name, e.g. `"The Atlantic"`, or empty),
`summary` (plain text), `long_summary`, `url` (the original article) and `read`, whether the player
has read it. `long_summary` is three or four short paragraphs separated by blank lines, at most 4,000
characters. It's left out when there isn't one, and the client shows `summary` instead.
The server sends it in reply to [`list_news`](#list_news) and [`read_news`](#read_news), and the
client shows the latest one. Hub subscribers don't know which connection a message came from, so the
reply goes to every client, which is fine with one player. A client ignores `news` while its news
panel is closed.

### `works`

`works`: residents' writing at the terminals, newest first. Each has its `work_id` (the F2 `Work`
id), `title`, `artist` (`id` and `name`), `form`, `text` (the piece itself, line breaks and all),
`statement` (the artist on what it's saying), `created` (sim time) and `read`, whether the player
has read it. `form` is the work's own, copied from the artist's craft when they made it, so it
doesn't change if their craft does. The server sends it in reply to [`list_works`](#list_works) and
[`read_work`](#read_work), to every client, as with `news`.

`notices`: the notice board beside the works, newest first. A notice is a shopkeeper's offer, event
or invitation, not a work, so it's never in `works`. Each has its `notice_id`, `title`, `text`,
`poster` (`id` and `name`) and `created` (sim time). It's empty while nobody has put one up.

### `murals`

`walls`: every wall that takes a mural, painted or not. The server sends it after the `snapshot`
and `clock` on connect, and again to everyone whenever a mural changes, and the client replaces
what it had.

| Field | Type | |
|---|---|---|
| `id` | string | The wall's id. |
| `map` | string | The map it's on, such as a street on side-view maps. Left out on the village, so it was absent from every wall on the isometric maps: read it as `wall.map ?? 'village'`. |
| `x`, `y` | integer | The building's tile at the west end of a south face or the north end of an east face: on its south row or east column, whatever storeys the mural spans. The face runs along that tile's south edge (`y + 1`) or east edge (`x + 1`). On a side-view map, the standing cell at the wall's west end, on the street in front of it. |
| `width` | integer | Tiles, running east from (`x`, `y`) for a south face, or south for an east face. |
| `face` | `"south"` or `"east"` | Which way the wall faces. Every wall on the side-view maps faces `"south"`, the camera; `"east"` was only on the isometric village. |
| `bottom`, `top` | number | The mural's lower and upper edges, in storeys up from the ground there: `0` is the ground and `1` the top of the ground floor. Fractions are fine, and `top` is above `bottom`. |
| `mural` | `Mural` or `null` | What's painted there now, or `null` while it's blank. |

A `Mural` has its `work_id`, `title`, `artist` (`id` and `name`), `statement`, and `image`, the URL
of its picture, `/api/works/<work_id>.png`. A new mural is a new work with its own id, so the URL
changes when the wall is painted over. A mural's F2 `Work.wall` is the wall's `id`.

### `paintings`

`frames`: every `painting` interactable, hung or empty. As with `murals`, the server sends it after
the `snapshot` and `clock` on connect, and again to everyone whenever a painting changes, and the
client replaces what it had. Clients that predate the gallery ignore it.

| Field | Type | |
|---|---|---|
| `id` | string | The F2 `Interactable`'s id, e.g. `"painting_1"`. |
| `map` | string | The map the interactable is on, e.g. `"gallery"`. |
| `painting` | `Painting` or `null` | What hangs there now, or `null` while the frame is empty. |

A `Painting` has its `work_id` (an F2 `Work` with the `painting` medium), `title`, `artist` (`id`
and `name`), `statement`, and `image`, the URL of its picture on the sim server. The client uses
`image` as given. Each work has its own URL, so it changes when a new painting replaces one. A
painting's F2 `Work` has no `wall` and doesn't say where it hangs.

### `player_state`

`player`: the player's money, what they carry, their body, their vitals and what they know, an F2
`Player` (`server/simile/schema/player.py`). The server sends it after the `snapshot` and `clock`
on connect, and again whenever any of it changes, and the client replaces what it had. Hunger,
power, health, an effect's strength and a lamp's charge change all the time, so a change to them
alone is sent once one of them has moved by 0.01 or more since the last `player_state`; any other
change is sent at once. Clients that predate it ignore it.

| Field | Type | |
|---|---|---|
| `money` | number | At least 0, in the same units as the residents' money. |
| `items` | `Item[]` | What they carry. A new player carries only the lamp. |
| `carry_limit` | number | The most they can carry, in kg. Picking things up keeps the items' total `weight` within it. |
| `body` | `Body` | What's become of each part of their body that can be sold or replaced. |
| `hunger` | number | From 0, fed, to 1, starving, when they collapse. |
| `power` | number | Their power cell's charge, from 1, full, to 0, flat, when they collapse. They run on it in place of hunger once a cell is in their `stomach`, and it stays full without one. Left out while it's full: read it as `player.power ?? 1`. |
| `health` | number | From 1, unhurt, to 0, when they collapse. Left out while it's full: read it as `player.health ?? 1`. |
| `effects` | `Effect[]` | Their ailments, in the order they got them, each kind once. Left out while there's none. |
| `mind` | `Mind` | What they know: the recipes they've learned, and those they've sold. Left out while they know none. |
| `left` | `Pile[]` | What they left lying in the world, oldest first: what they carried when they collapsed, and anything of a pickup that didn't fit. Left out while there's none. |
| `taken` | object | When each pickup in the world was last emptied, by the player or a recycler bot, a timestamp by pickup id. Salvage lies there again a while after it was taken; a secret, cash or a ration, stays taken for good. Left out while there's none. |
| `sales` | `Sale[]` | What they've sold that its buyer keeps for them to buy back, oldest first. Left out while there's none. |
| `searched` | `string[]` | The searchable things and jacks they've searched, by interactable id, in the order they searched them. Each is searched once, and holds nothing after. Left out while there's none. |

Power is what hunger becomes once the power cell is fitted, but it's a field of its own rather than
hunger read the other way. It runs from full to flat like the lamp's `charge`, and charges at a
plug as the lamp does, while hunger keeps meaning what it always has for every client that reads
it. The client shows `power` while a power cell is in the `stomach`, and `hunger` otherwise.

An `Effect` has its `kind`: `"rat_bite"`, `"infection"`, what an untreated bite can turn into, or
`"radiation"`; its `strength`, above 0 and at most 1; `fades`, the strength it loses each sim hour,
or `null` while it lasts until it's treated, at the clinic or with medicine; and `since`, when they
got it. A fading effect is gone once its strength reaches 0.

A `Sale` has the `item` they sold, the `place` of the buyer that keeps it, and its `price`, what it
fetched. The buyer offers it back in its `stock`.

Beside `player`, the message has `meal`: the meal on offer where the player stands, which they can
have by sending [`eat`](#eat) without an item. It's left out where there's none. A `Meal` has its
`place`, the location id of their home or the shop; its `name`, as the player sees it, `"home"` or
the shop's name, such as `"Golden Bowl Noodles"`; and its `price`, 0 at home. A shop offers one only
while it's serving, as it would feed a resident. The server sends a new `player_state` when the
player walks into or out of a place with a meal.

Where a shop sells meals but isn't serving them, the message has `shut` in place of `meal`: it's
left out everywhere else, and never sent beside a `meal`. A `Shut` has the shop's `place` and
`name`, as a `Meal` does; its `reason`, `"closed"` while it isn't serving, off shift or past
last orders as the Daily Grind is after 17:00 while its barista finishes the queue, or
`"sold_out"` while it's open but its batch for this shift has gone, as the noodle bar's can; and
`opens`, the timestamp it next starts serving. That's the next start after now of the shifts of
whoever works there: a forecast, so a keeper who comes late or skips a shift makes it wrong, and
while a keeper is due but hasn't come it's their next shift, not the one they're missing. It's
`null` when nobody works there, or they have no shifts. The server sends a new `player_state` when
a shop the player stands in starts or stops serving.

It also has `buyer`: who buys things where the player stands, which they sell to with
[`sell`](#sell). It's left out where there's none. A `Buyer` is a stall, such as the scrap trader's,
or a keeper at their place, such as the clinic's doctor. It has its `place`, a location id such as
`"scrap_stall"`; its `name`, as the player sees it, such as `"The scrap trader"`; and its `prices`,
what it pays for one of each thing the player carries that it buys, by item `id`:
`{"copper_wire": 6}`. That's empty when they carry nothing it buys. The prices are the server's, and
a resident only voices them. The server sends a new `player_state` when the player walks up to a
buyer or away from one.

A keeper such as the clinic's doctor may also buy parts of the player's body and fit bionics:

- `parts`: what it pays for each part of their body it would buy now, keyed by `BodyPart`, which
  they sell with [`sell_part`](#sell_part): `{"left_kidney": 100}`. The clinic's doctor buys one
  kidney, never the second. It's left out while it would buy none, as at the scrap trader's stall,
  or at the clinic once they've sold a kidney.
- `fittings`: the bionics it would fit now, whether or not they can pay, each once, which they have
  fitted with [`fit`](#fit). It's left out while there are none. A `Fitting` has its `bionic`; its
  `name`, as the player sees it, such as `"Spring feet"`; its `price`; and its `parts`, the parts
  of their body it can go in place of, any one of which they give up for it: `["legs"]`, or
  `["left_eye", "right_eye"]` for the infrared eye. Each part is named once, and only a part the
  bionic can replace. A grade of a line past the first goes in place of the grade before it, which
  the doctor takes back.
- `recipes`: what it pays for each recipe they know that it would buy now, keyed by the `Bionic`
  it builds, which they sell with [`sell_recipe`](#sell_recipe): `{"datajack": 40}`. It buys each
  recipe once. It's left out while it would buy none.
- `treatments`: what it would treat now, whether or not they can pay, each once, which they pay for
  with [`treat`](#treat): patching them up while they're hurt, and each effect they have that it
  treats. It's left out while there's nothing. A `Treatment` has its `effect`, the `EffectKind` it
  treats, or `null` for patching up their health to full; its `name`, as the player sees it, such
  as `"Patch up"`; and its `price`.

And any buyer may sell:

- `stock`: what it sells now, whether or not they can pay, which they buy with [`buy`](#buy). Each
  `Offer` has its `item`, as they'd carry it, and its `price`. The scrap trader sells back what
  they sold it, from their `sales`. It's left out while there's nothing.

Like `prices`, these are the server's, and so is the stock: what the keeper would buy, fit or sell
now is already in them. The keeper only voices them, and talking can't change them.

`player_state` also has `recipes`: each recipe in `player.mind`, in full and in the same order. It's
left out while they know none. A `Recipe` has the `bionic` it builds; its `name`, as the player sees
it, such as `"Datajack"`; its `parts`, the items the fitting uses up, how many of each by item `id`:
`{"copper_wire": 3, "usb_c_connector": 1}`; its `credits`, what the fitting costs from their money;
`replaces`, the parts of their body it can go in place of, any one of which they give up for it, or
a lower grade of its line fitted there; and `after`, what must be fitted first, each of them or a
higher grade of its line: a power cell, for everything but a cell. The clinic fits only what they
have a recipe for.

And it has `piles`: what's lying in the world for the player to pick up besides what they left,
such as salvage and secrets, as `Pile`s on every map. It's left out while there's none. A pile in
`piles` that they take everything from is gone from the next `player_state`, and one they take only
some of is in their `left` from then on, with what didn't fit. Salvage comes back a while after
it's taken, in a later `player_state`, and a secret never does.

An `Item` has its `id`, what it is, the same for every one of its kind (`"copper_wire"`, `"lamp"`),
which prices salvage; its `kind`, `"salvage"`, `"food"`, `"lamp"` or `"part"`, something found that
the doctor fits with a bionic and nobody buys; its `name`, as the player sees it; its `weight` in
kg; `charge`, a lamp's battery from 0 (flat) to 1 (full); and `on`, whether a lamp is switched on,
running its battery down. `charge` and `on` are `null` for anything else. The player switches the
lamp with [`lamp`](#lamp). It runs down while it's on, and while they stand at a plug it charges, on
or off. When its battery runs flat it goes off by itself.

A `Pile` is things lying on a tile in the world for the player to pick up with
[`pick_up`](#pick_up): its `items`, `money`, cash that weighs nothing, and `at`, a `MapTile` (`map`,
`x` and `y`, whole tiles). It holds at least one item or some money, and `money` is left out while
it's 0. What they left when they collapsed is one kind, in `left`, each on the tile they fell on or
the ground below it. Salvage and secrets, in `piles`, are another.

A `Body` has a field for each part: `legs`, `vertebra`, `left_eye`, `right_eye`, `left_kidney`,
`right_kidney`, `stomach` and `feet`. Each is `"present"`, `"sold"`, or the bionic fitted in its
place: a grade of legs in the legs, `"datajack"` in the vertebra, `"infrared_eye"` in one eye or the
other, never both, a power cell in the stomach, or a grade of feet in the feet. `stomach` and `feet`
are left out while they're `"present"`, so a body from before them reads the same. A `BodyPart` is
one of those eight field names.

Three bionics come in a line of grades, each grade better than the one before:

- the power cell, in place of the stomach: `"power_cell"`, `"power_cell_2"` and `"power_cell_3"`.
  It runs every other bionic, and a bigger cell runs more of them.
- the legs, for speed and kick: `"bionic_legs"`, `"bionic_legs_2"` and `"bionic_legs_3"`.
- the feet, for jump height: `"spring_feet"` and `"spring_feet_2"`.

`mind` is what they know, a `Mind`. They keep it when they collapse, and later when they die. It has
`recipes`, the recipes they know, each by the `Bionic` it builds, in the order they learned them;
and `sold`, those they've sold to the clinic, in the order they sold them. They still know a recipe
they've sold, and can't sell it again. `sold` is left out while there's none, and `mind` while they
know no recipe.

The player's state is saved with the world. A save from before it loads with the starting player:
a whole body, no money and a fully charged lamp, switched off, with nothing left anywhere, nothing
taken and nothing known. A save from before the stomach, the feet and the mind loads with them
still their own and knowing nothing. One with stage 1's legs loads them as the lines: the hydraulic
and spring legs as the spring feet's first and second grades, with their own legs back, unless
higher feet are already fitted; the sprint and blade legs as the legs' first and second; and the
premium legs as the top grade of both. One from before vitals loads at full power and health, with
no effects and nothing to buy back. One from before searching has searched nothing. Their
humanity is part of it on the server, derived from the bionics fitted (`Player.humanity`), but it's
never sent: the player sees it only in how residents treat them.

### `player_collapsed`

`position`: where the player wakes, at home. `cause`: the `Vital` that ran out, why they
collapsed: `"hunger"`, they starved; `"power"`, their power cell ran flat; or `"health"`, they had
none left. The client puts them at `position`, snapping there as through a door, and can say what
happened. They wake with their lamp, switched off, so they can see to go back once they switch it on. Everything else they carried stays where they
fell: the [`player_state`](#player_state) that follows has it in a new `Pile` at the end of `left`.
With nothing but the lamp, they leave no pile. Clients that predate it ignore it.

### `journal`

`entries`: what the player has learned about the incident, in the order they learned it, each an
F2 `JournalEntry` (`server/simile/schema/story.py`). The server sends it after the `snapshot` and
`clock` on connect, and again whenever an entry is added or a lead is followed, and the client
replaces what it had. There's no request for it: the client keeps the last one for when the player
opens the journal. Clients that predate it ignore it.

| Field | Type | |
|---|---|---|
| `fact_id` | string | The fact it's about. Several entries can be about one fact: two witnesses, or a lie and then the truth. |
| `text` | string | What the player learned, as the journal puts it. A lie is written as it was told: "Raymond says he was at home all night." |
| `source` | `Source` | Who told them, or the clue they found it in. |
| `learned` | string | When, in sim time. |
| `flushed` | boolean or `null` | Whether the infrared eye saw the resident flush as they told it. The eye shows a flush exactly on a lie, as the code decides it, so `true` is a lie it caught and `false` the truth. `null` if the player had no infrared eye then, and always for a clue. |
| `leads` | `Lead[]` | The leads it opened that are still open: its fact's leads, and none for a lie. |

A `Source` has its `kind`, `"resident"` if a resident told them or `"clue"` if they found it (in
Aris's notes, at a terminal or in the sewers); its `id`, the resident's or the clue's
interactable's; and its `name`, as the journal shows it.

A `Lead` has its `fact_id`, the fact that following it turns up, and its `text`, what to follow up:
"Kofi paints in the lane at night. Ask him what he saw."

Two rules decide which leads are open:

- **A lie opens no leads.** Its entry is about the fact it hides, and that fact's leads would give
  the truth away.
- **Any entry about a fact closes the leads to it, a lie included.** Asking Raymond where he was
  follows the lead whatever he says. The journal doesn't record which entries are lies (`flushed`
  shows only what the eye saw), so this is the only rule the server can apply after a restart.

The incident and its facts (F2's `Incident` and `Fact`) stay on the server: who did it, why, who
knows what and who lies about it are never sent. The client sees only what the player has learned.

### `audio_chunk`

A binary frame: part of a line's audio, as Qwen3-TTS produces it. A 12-byte header, then the
samples. All integers are little-endian.

| Offset | Size | Type | Field |
|---|---|---|---|
| 0 | 4 | uint32 | Line id: the `line.id` of the `line` message it voices. |
| 4 | 4 | uint32 | Sequence number: 0 for a line's first chunk, then 1, 2, … |
| 8 | 1 | uint8 | Flags. Bit 0 is set on the line's last chunk. The other bits are 0. |
| 9 | 3 | | Reserved, 0. Keeps the samples 4-byte aligned. |
| 12 | 2 × n | int16[n] | Samples: 24 kHz, mono, 16-bit signed PCM. n may be 0. |

The frame is always an even number of bytes. Senders send the `line` message before any of its
chunks, and its chunks in sequence order. A line's audio may stop early, for example when the player
walks out of earshot, so its last chunk can be empty, with only the flag set.

Example: line 7, chunk 2, last, samples 1, -2, 32767:

```
07000000 02000000 01000000 0100 feff ff7f
```

`AudioChunk.encode` and `.decode` in `server/simile/protocol/audio.py`, and `encodeAudioChunk` and
`decodeAudioChunk` in `client/src/net/audio.ts`, both test against these bytes.

## Client → server

### `player_move`

`position`. The client sends the player's position as it changes, and the server takes it as it
is. Going through a door is a `player_move` with the other map's `map`. A position without `map`
puts the player on the village. Side-view maps have no village, so there the server ignores a
position without `map`, as it ignores a position on any map it doesn't know.

On a side-view map the player can jump and fall, so a position can be mid-air. The server keeps a
position in open air, over somewhere to land, if either:

- it's within the farthest and highest jump the player can make from somewhere to stand: a run
  jump with Space held, taking off as late as coyote time allows. Its reach along the row and its
  height are set in one place, which the client's jump and the server's check both read, and
  they're the player's own, by the legs fitted (`player_state`'s `body`); or
- it's lower than the last position the server kept on that map, and within that jump's reach of
  it along the row, as in a fall from any height, which lands safely.

It ignores a position nobody could be at: inside something solid, off the map, over nothing to
land on, or higher than any jump without being a fall within reach of the last position kept. It
never moves the player back onto the ground: the next `player_move` says where they landed. The player's entity is still `standing` in a jump, as
the server doesn't track the player's pose.

The server keeps the last position it was sent, so a [`snapshot`](#snapshot), after a reload or a
reconnection, can put the player mid-air. The client lets them fall from there.

### `player_say`

`text` (not empty) and `target`, the id of the NPC the player is talking to.

### `eat`

`item`: one of the food items the player carries, by its `id`, or `null` for the meal on offer
where they stand, `player_state`'s `meal`. The item is eaten, or the meal paid for and eaten, and
either relieves their hunger. The server sends the [`player_state`](#player_state) that follows. It
ignores an `eat` for an item they don't carry or that isn't food, and one for a meal where there's
none on offer or that they can't pay for.

### `pick_up`

No fields. Picks up from the nearest `Pile` on the map the player is on, within a tile and a half of
where they stand, one of their `left` or of `player_state`'s `piles`. It takes its money, and each
item, in order, that still fits under their carry limit, and skips any that doesn't, which stays in
the pile with anything else left. The server sends the [`player_state`](#player_state) that follows,
and ignores a `pick_up` with nothing in reach, or with only items that don't fit.

It also reaches clues (S13): a clue whose cell is within half a tile of the player, and the clue
in a jack whose `stand` tile they're on, with the datajack fitted. The nearer of a clue and a pile
is taken, the pile if they're as near. A clue found writes each fact in it to the journal, and the
server sends the [`journal`](#journal) that follows rather than a `player_state`.

And it searches (P3): a searchable thing whose `stand` tile the player is on, or a jack with the
datajack fitted that has `items`, `money` or `teaches`, that isn't in their `searched` yet, before
any pile or clue. A jack with a clue and something to search gives what it holds first, and its
clue on the next `pick_up`. They learn the recipe it `teaches`, if it's new to them, and take its
`money` and `items` as from a pile. What doesn't fit under their
carry limit is left where they stand, a new `Pile` at the end of their `left`. It's in their
`searched` from then on, even if it held nothing, and the server sends the
[`player_state`](#player_state) that follows. The client knows what it held from the maps.

### `sell`

`item`: one thing the player carries, by its `id`, or `null` for everything they carry that the
buyer where they stand buys, `player_state`'s [`buyer`](#player_state). Each is sold for the
buyer's price in `prices`, which goes to their `money`. The server sends the
[`player_state`](#player_state) that follows. It ignores a `sell` where there's no buyer, and one
for an item they don't carry or the buyer doesn't buy.

### `lamp`

`on`: `true` to switch on the lamp the player carries, `false` to switch it off. The server sends
the [`player_state`](#player_state) that follows. It ignores a `lamp` if they carry no lamp, if it's
already on or off as asked, and for switching on a flat one.

### `sell_part`

`part`: a part of the player's body, a `BodyPart` such as `"left_kidney"`, that the buyer where
they stand buys, by `player_state`'s [`buyer`](#player_state)'s `parts`. It's sold for that price,
which goes to their `money`, and the part is `"sold"` in their `body` from then on. The server sends
the [`player_state`](#player_state) that follows. It ignores a `sell_part` where there's no buyer,
and one for a part the buyer won't buy.

### `fit`

`bionic` and `part`: one of the bionics the buyer where they stand fits, by `player_state`'s
[`buyer`](#player_state)'s `fittings`, and the part of their body it goes in place of, one of that
fitting's `parts`. They pay its `price` from their `money`, and the bionic is in that part of their
`body` from then on. The server sends the [`player_state`](#player_state) that follows. It ignores
a `fit` where there's no buyer, for a bionic it doesn't fit, for a part the bionic can't go in
place of, and one they can't pay for.

### `sell_recipe`

`recipe`: a recipe the player knows, by the `Bionic` it builds, that the buyer where they stand
buys, by `player_state`'s [`buyer`](#player_state)'s `recipes`. It's sold for that price, which
goes to their `money`, and it's in their `mind`'s `sold` from then on. They still know it. The
server sends the [`player_state`](#player_state) that follows. It ignores a `sell_recipe` where
there's no buyer, and one for a recipe the buyer won't buy, which includes any they've sold.

### `buy`

`item`: the `id` of something the buyer where the player stands sells, in `player_state`'s
[`buyer`](#player_state)'s `stock`. They buy the first offer of that `id` for its `price`, from
their `money`, and carry it from then on. The server sends the [`player_state`](#player_state) that
follows. It ignores a `buy` where there's no buyer, for something not in its `stock`, one they
can't pay for, and one that won't fit under their carry limit.

### `treat`

`effect`: one of the treatments the buyer where they stand gives, by `player_state`'s
[`buyer`](#player_state)'s `treatments`: an `EffectKind` to treat, or `null` to be patched up. They
pay its `price` from their `money`. The server sends the [`player_state`](#player_state) that
follows. It ignores a `treat` where there's no buyer, for a treatment it doesn't give now, and one
they can't pay for.

### `kick`

`facing`: a `SideFacing`, as a creature's is: `"east"` to kick right, or `"west"` to kick left. The
player kicks from where the server last kept them ([`player_move`](#player_move)), and the server
decides what it hits, as it runs the creatures: a creature it hurts changes `state`, in a
[`creature_moved`](#creature_moved), or is gone, in a [`creature_gone`](#creature_gone). The client
plays the kick itself. The server ignores a `kick` off a side-view map.

### `watch_npc`

`npc_id`: the NPC whose [`npc_state`](#npc_state) the debug overlay wants, or `null` to stop. The
client sends it when the overlay opens on an NPC or switches to another, and with `null` when the
overlay closes. Each one replaces the last, so there's one watched NPC at most. Nothing is watched
until the client sends one, so it sends it again after each `snapshot`: a reconnection may be to a
restarted server.

### `list_news`

No fields. The client sends it when the player opens the news at a terminal, and the server
replies with [`news`](#news).

### `read_news`

`news_id`: the article the player reads. The server stores it as the player's own `news` memory,
with its `news_id`, and replies with [`news`](#news), where it's now `read`. An unknown `news_id`
stores nothing, and still gets a `news` reply.

### `list_works`

No fields. The client sends it when the player opens residents' writing at a terminal, and the
server replies with [`works`](#works).

### `read_work`

`work_id`: the work the player reads. The server stores it as the player's own `work` memory, with
its `work_id`, and replies with [`works`](#works), where it's now `read`. An unknown `work_id`
stores nothing, and still gets a `works` reply.

## Sim events

`server/simile/protocol/lifespan.py` forwards the sim's bus events to every client:

| Sim event | Message |
|---|---|
| `EntityMoved` | `entity_moved` |
| `ConversationStarted` | `conversation_started` |
| `LineSpoken` | `line`, with `voiced` from `app.state.voiced(line)` while earshot voicing (I1) runs, else `false` |
| `ConversationEnded` | `conversation_ended`, with the clock's time if the conversation's `ended` isn't set |

So most modules publish on the bus rather than calling the hub.

## Using it on the server

`hub_of(app)` returns the `Hub` for the running server, creating it on first use, so any module can
get it from its lifespan whatever the lifespan order.

```python
from simile.protocol import EntityMovedMessage, PlayerSayMessage, Position, hub_of

hub = hub_of(app)
hub.broadcast(EntityMovedMessage(entity_id="mei", position=Position(x=4.5, y=6)))
hub.broadcast(audio_chunk)  # an AudioChunk goes out as a binary frame
unsubscribe = hub.subscribe(PlayerSayMessage, on_player_say)
stop = hub.greet(current_murals)  # returns a server message, or None to send nothing
hub.snapshot = world_snapshot  # returns a SnapshotMessage; the fixtures at sim time by default
```

- `broadcast` queues the message for every connected client and returns at once, so it's safe to
  call from a tick or an event bus handler. Each client gets its messages in the order they were
  broadcast, after its snapshot.
- The protocol lifespan sets `hub.clock`, which sends the `clock` after each snapshot. Without the
  lifespan, a new client gets only the snapshot.
- `greet(greeter)` adds a message for each new client, such as `murals` or `paintings`. The hub
  calls every greeter after the snapshot and clock, in the order they were added, and sends what
  each returns unless it's `None`, before any broadcast. One that raises is logged and skipped. Call
  the returned `stop()` when your lifespan exits.
- Subscribers to client messages are called on the event loop, in the order they subscribed, and
  mustn't block. One that raises is logged and doesn't affect the others.
- Call the hub from the event loop. From a worker thread, such as a TTS model running in one, use
  `loop.call_soon_threadsafe(hub.broadcast, chunk)`.

## Using it on the client

```ts
import { server } from '../net';

server.on('snapshot', (snapshot) => world.reset(snapshot));
server.on('entity_moved', ({ entity_id, position }) => world.move(entity_id, position));
server.on('audio_chunk', ({ lineId, sequence, last, samples }) => audio.play(lineId, samples));
server.send({ type: 'player_move', position: { x: 14, y: 12.5 } });
```

- `server.on(type, handler)` takes any server message `type` or `'audio_chunk'`, types the handler's
  argument to match, and returns a function that unsubscribes.
- `server` connects to `/ws` on the page's origin when `client/src/net/` loads, at startup.
  Messages aren't replayed, so subscribe when your module loads. A scene that starts later should
  read state that a module-level subscriber keeps.
- Under vitest it doesn't connect, so tests can import it. `server.dispatch(text)` or
  `server.dispatch(arrayBuffer)` handles a frame as if the server had sent it, which also suits dev
  harnesses, and `vi.spyOn(server, 'send')` sees what a module sends.
- After a disconnection it reconnects with backoff (250 ms, doubling, at most 5 s), and the server
  sends a fresh `snapshot`.
- `send` returns `false` and drops the message while disconnected.

## Changing a message

1. Change the models in `server/simile/protocol/messages.py`. Changes to the protocol go in their
   own PR.
2. `cd server && uv run simile protocol` writes `server/simile/protocol/protocol.schema.json`.
3. `cd client && npx vitest run src/net/protocol.test.ts -u` regenerates `client/src/net/protocol.ts`.
4. Update this document, and commit all of them.

CI fails if either generated file is out of date: `server/tests/protocol/test_export.py` checks the
JSON Schema, and `client/src/net/protocol.test.ts` checks the TypeScript.
