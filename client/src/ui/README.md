# Dialogue UI

The text side of conversations, drawn as HTML over the game canvas by `DialogueScene`:

- a speech bubble over each speaker within earshot, for the line's `duration`, fainter the further
  away they are;
- a chat box: Enter opens it to the nearest NPC within range, Enter sends `player_say`, Esc closes;
- a scrollable log of everything the player has heard or said.

Distances and timings are in [`tuning.ts`](tuning.ts).

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
- `chatTarget(view)` picks who the chat box talks to, and `ChatBox.open(target)` opens it to a given
  NPC, for example when an NPC starts a conversation with the player.
