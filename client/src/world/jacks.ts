import { fitted } from '../dolls/bionics';
import type { Body } from '../net';
import { maps } from './assets';
import type { Interactable } from './interactables';
import { objectsOf, type TiledMap } from './map';

export const DOORS_LAYER = 'doors';

/** Whether the datajack is fitted, which works the jacks. */
export const jacked = (body?: Body): boolean => fitted(body).includes('datajack');

/** Whether a link leaves from one of the jack's stand tiles, as the lift's does, so it's taken as a door. */
export function leadsAway(jack: Interactable, map: TiledMap | undefined = maps[jack.map]): boolean {
  if (!map) return false;
  return objectsOf(map, DOORS_LAYER).some(({ x = 0, y = 0 }) =>
    jack.stand.some((tile) => tile.x === Math.floor(x / map.tilewidth) && tile.y === Math.floor(y / map.tileheight)),
  );
}

/** What E at a jack says without the datajack. */
export const deadJack = (jack: Interactable): string =>
  `Nothing happens: the ${jack.label.charAt(0).toLowerCase()}${jack.label.slice(1)} needs a datajack.`;
