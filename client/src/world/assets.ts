import { dolls } from '../dolls/assets';
import { isPlayerFigure, PLAYER_FIGURE, PlayerBody } from '../dolls/bionics';
import type { FigureManifest } from '../dolls/manifest';
import { server } from '../net';
import type { TiledMap } from './map';

const files = import.meta.glob<string>(
  ['../../../content/street/*.tmj', '../../../content/street/floors/*.tmj'],
  { eager: true, query: '?raw', import: 'default' },
);

const fileName = (path: string) => path.slice(path.lastIndexOf('/') + 1, path.lastIndexOf('.'));

/** Every street and floor, by id. One object, never replaced, since `ui/side-view.ts` reads it. */
export const maps: Record<string, TiledMap | undefined> = {};
for (const [path, json] of Object.entries(files)) maps[fileName(path)] = JSON.parse(json) as TiledMap;

export const mapIds: readonly string[] = Object.keys(maps);

export { dolls };

const residentDolls = Object.keys(dolls)
  .filter((id) => !isPlayerFigure(id) && dolls[id]!.resident !== false)
  .sort();

/** What the player has fitted, from `player_state`. */
export const playerBody = new PlayerBody();
server.on('player_state', ({ player }) => playerBody.set(player.body));

function fnv1a(text: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 0x01000193);
  return hash >>> 0;
}

/** Its own doll, the player's for `body`, or a resident's picked by its id, the same every time. */
export function dollFor(id: string, body: PlayerBody = playerBody): FigureManifest {
  if (id === PLAYER_FIGURE) return dolls[body.figure] ?? dolls[PLAYER_FIGURE];
  return dolls[id] ?? dolls[residentDolls[fnv1a(id) % residentDolls.length]];
}
