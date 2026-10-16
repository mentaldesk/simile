# Dialogue UI

The text side of conversations, drawn as HTML over the game canvas by `DialogueScene`:

- a speech bubble over each speaker within earshot, for the line's `duration`, fainter the further
  away they are;
- a ring and name tag on the NPC the player will talk to (see *Choosing who to talk to*);
- a chat box: Enter opens it to that NPC, Enter sends `player_say`, Esc closes;
- an ellipsis over the NPC while they write their reply, until a line of theirs arrives or the
  conversation ends;
- a hint when an NPC starts a conversation with the player: "Mei wants to talk. Press Enter to
  reply.";
- a scrollable log of everything the player has heard or said, with an NPC's lines to the player
  marked "→ You".
- the news at a terminal (see *Reading the news*).

## Choosing who to talk to

The ringed NPC is, in order:

1. the one the player chose by clicking them or with Tab, while they're within `CHAT_RANGE_TILES`
   and not talking with someone else, or the player is talking with them;
2. the NPC the player is talking with, for as long as the server keeps that conversation going;
3. the nearest NPC within `CHAT_RANGE_TILES` who isn't talking with someone else.

Tab and Shift+Tab go through the NPCs the player can talk to, nearest first, in or out of the chat
box. NPCs talking with someone else are skipped: clicking one says they're busy, and clicking one
out of range says they're too far away. Esc forgets the choice. While the debug overlay is open,
clicks are its own.

Saying something to someone else mid-conversation ends the current conversation with a quick
goodbye from the NPC left behind: the server does that when `player_say` names a new NPC. While the chat box is open its target stays put, so the
label never changes under the player; if they walk off or get busy, sending says so instead.

Distances and timings are in [`tuning.ts`](tuning.ts). `CHAT_RANGE_TILES` (3) is a tile inside
the server's `say_range` (4), so an NPC the chat box picks is still in range when the line arrives.

## Reading the news

Near one of the map's `terminal` locations (`terminalAt` in [`world/terminals.ts`](../world/terminals.ts)),
a hint says "Press E to read the news", and E opens the news panel. It sends `list_news` and shows
the `news` that comes back: each article's title, source and the start of its summary, newest first,
with a tick on those the player has read. ↑ and ↓ choose an article, and Enter or a click reads it:
the panel sends `read_news` and shows the whole summary and a link to the original, which opens in a
new tab. The server stores what the player read as their own `news` memory, and residents who read
it too are told so when they talk with the player. Esc or E closes the panel, and so does walking
away from the terminal. The panel keeps its key-downs from `window`, like the chat input, so the
player doesn't walk while reading, and it ignores `news` while closed.

## Keys

The game's keys (Enter, Tab, Esc, E) are handled on `window` only when nothing on the page has
focus (`onGameKey` in [`keys.ts`](keys.ts)), so a focused link, button or input keeps its own Enter,
Tab and Esc.

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
have sent. Move with the arrow keys, WASD or a click on the ground. It only loads in `vite dev`:
builds leave it out.

## Extending it

- `dialogue.say(text, target)` sends `player_say`, then shows and logs the player's line. `line`
  messages spoken by the player are skipped because they've been shown already.
- `dialogue` follows `snapshot`, `conversation_started` and `conversation_ended`: `partner()` is the
  NPC the player is talking with, `busy(id)` whether an NPC is talking with someone else, and
  `onInvitation(listener)` hears about NPCs who start a conversation with the player.
- `ChatTarget` (`target.ts`) picks who the chat box talks to, and `clicked(point, view)` finds the
  NPC a click picks with `world/hit.ts`. Another overlay that wants clicks while it's open calls
  `claimClicks(() => open)`.
