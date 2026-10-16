# Dialogue UI

The text side of conversations, drawn as HTML over the game canvas by `DialogueScene`:

- a speech bubble over each speaker within earshot, for the line's `duration`, fainter the further
  away they are;
- a chat box: Enter opens it to the NPC the player is talking with, for as long as the server keeps
  that conversation going, or else the nearest NPC within `CHAT_RANGE_TILES` who isn't talking to
  someone else. Enter sends `player_say`, Esc closes;
- an ellipsis over the NPC while they write their reply, until a line of theirs arrives or the
  conversation ends;
- a hint when an NPC starts a conversation with the player: "Mei wants to talk. Press Enter to
  reply.";
- a scrollable log of everything the player has heard or said, with an NPC's lines to the player
  marked "→ You".

Distances and timings are in [`tuning.ts`](tuning.ts). `CHAT_RANGE_TILES` (3) is a tile inside
the server's `say_range` (4), so an NPC the chat box picks is still in range when the line arrives.

## What the world scene provides

The UI needs three things from the world scene (C1). Implement `WorldView` and register it when the
scene starts. Import from `ui/world-view`, not `ui`, so tests don't load Phaser.

```ts
import { setWorldView } from '../ui/world-view';

// in the world scene's create()
const unregister = setWorldView({
  positionOf: (id) => ...,
  npcIds: () => ...,
  bubbleAnchor: (id) => ...,
});
this.events.once(Phaser.Scenes.Events.SHUTDOWN, unregister);
```

| Method | Returns |
|---|---|
| `positionOf(id)` | Where an entity is now, in tiles as in the protocol, or `undefined`. Include the player as `"player"`, at the position the client sends in `player_move`. |
| `npcIds()` | The id of every NPC in the world. |
| `bubbleAnchor(id)` | Where to pin the entity's bubble: the top centre of its sprite, in game-canvas pixels after the camera's scroll and zoom, or `undefined`. Off-screen points are fine; bubbles stay on screen. |

The UI calls these every frame, after the world scene's `update`. Until a view is registered it uses
`TrackedWorld`, which follows `snapshot` and `entity_moved` and centres a 48 px-tile camera on the
player.

The chat input stops its key-downs from reaching `window`, so the game's keys (Phaser's keyboard
included) don't fire while the player types. Key-ups still get through, so no key sticks down.

## Dev harness

Run `make dev-client` and open <http://localhost:5173/?harness=dialogue>. The harness disconnects
from the sim server, plays fake lines through `server.dispatch` (Mei and Viktor talking nearby, Suki
further off, Tom out of earshot), draws boxes for the entities and lists every `player_say` it would
have sent. Move with the arrow keys, WASD or a click. It only loads in `vite dev`: builds leave it out.

## Extending it

- `dialogue.say(text, target)` sends `player_say`, then shows and logs the player's line. `line`
  messages spoken by the player are skipped because they've been shown already.
- `dialogue` follows `snapshot`, `conversation_started` and `conversation_ended`: `partner()` is the
  NPC the player is talking with, `busy(id)` whether an NPC is talking with someone else, and
  `onInvitation(listener)` hears about NPCs who start a conversation with the player.
- `chatTarget(view, dialogue)` picks who the chat box talks to, and `ChatBox.open(target)` opens it
  to a given NPC.
