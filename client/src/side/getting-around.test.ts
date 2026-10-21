import { describe, expect, it } from 'vitest';
import { village } from './content';
import { isStanding, type Cell, type SideMap } from './maps';
import { SidePlayer, spanEnd, type Controls, type MapPosition } from './player';
import { climbRuns } from './runs';
import { chosen, CLIMB_REACH, type Press, type Way } from './ways';

const idle: Controls = { x: 0, y: 0, use: false };
const EDGE = CLIMB_REACH - 0.1;
const OFFSETS = [-EDGE, -1, -0.5, 0, 0.5, 1, EDGE];
const maps = [...village.maps.values()];
const climbs = maps.flatMap(({ links }) => links.filter(({ kind }) => kind === 'stairs' || kind === 'ladder'));

function hold(player: SidePlayer, controls: Controls, seconds: number): void {
  for (let t = 0; t < seconds; t += 1 / 60) player.update(controls, 1 / 60);
}

/** Starts with E, then holds up or down; or just holds up or down. Undefined if that key takes another way here. */
function climb(at: MapPosition, press: Press, up: boolean, isIt: (way: Way) => boolean): SidePlayer | undefined {
  const player = new SidePlayer(village, at);
  const map = village.map(at.map)!;
  const way = chosen(player.ways(), press === 'use' ? 'use' : up ? 'up' : 'down', map);
  if (!way || !isIt(way)) return undefined;
  const y = up ? -1 : 1;
  if (press === 'use') player.update({ ...idle, use: true }, 1 / 60);
  hold(player, { ...idle, y }, 8);
  return player;
}

/** Up to the far edge of the tile either side of `end` along its row, where the player can stand. */
function around(map: SideMap, end: Cell): number[] {
  return OFFSETS.map((offset) => end.x + offset).filter((x) => isStanding(map, Math.floor(x + 0.5), end.y));
}

describe('every flight and ladder between floors', () => {
  it('has each end where walking along its row gets to from anywhere on it', () => {
    for (const link of climbs) {
      const map = village.map(link.map)!;
      for (let x = 0; x < map.width; x++) {
        if (!isStanding(map, x, link.y)) continue;
        const [low, high] = [spanEnd(map, x, link.y, -1), spanEnd(map, x, link.y, 1)];
        expect(low <= link.x && link.x <= high, `${link.id} from ${x} on ${map.id}`).toBe(true);
      }
    }
  });

  it('takes the player to its other end from anywhere in the tile either side, on up or down, or E then up or down', () => {
    for (const link of climbs) {
      let climbed = 0;
      const far = village.far(link)!;
      const up = village.map(far.map)!.floor > village.map(link.map)!.floor;
      const isIt = (way: Way) => 'link' in way && way.link === link;
      for (const x of around(village.map(link.map)!, link)) {
        for (const press of ['use', 'up'] as const) {
          const player = climb({ x, y: link.y, map: link.map }, press, up, isIt);
          if (!player) continue;
          climbed++;
          expect(player.mapPosition, `${link.id} from ${x} on ${link.map} by ${press}`).toEqual({
            x: far.x,
            y: far.y,
            map: far.map,
          });
        }
      }
      expect(climbed, link.id).toBeGreaterThan(0);
    }
  });
});

describe('every flight and ladder on a street', () => {
  it('takes the player from either end to the other from anywhere in the tile beside it', () => {
    for (const map of maps.filter(({ kind }) => kind === 'street')) {
      for (const run of climbRuns(map)) {
        const [foot, head] = [run.path.points[0], run.path.points.at(-1)!];
        for (const [from, to, up] of [
          [foot, head, true],
          [head, foot, false],
        ] as const) {
          const isIt = (way: Way) => 'run' in way && way.at.x === from.x && way.at.y === from.y;
          let climbed = 0;
          for (const x of around(map, from)) {
            for (const press of ['use', 'up'] as const) {
              const player = climb({ x, y: from.y, map: map.id }, press, up, isIt);
              if (!player) continue;
              climbed++;
              expect(player.climbing, `${map.id} from ${x}, ${from.y} by ${press}`).toBeUndefined();
              expect(player.position).toEqual({ x: to.x, y: to.y });
            }
          }
          expect(climbed, `${map.id} from ${from.x}, ${from.y}`).toBeGreaterThan(0);
        }
      }
    }
  });
});

describe('every lift', () => {
  it('takes the player to its floor on E from its cell', () => {
    for (const link of maps.flatMap(({ links }) => links.filter(({ kind }) => kind === 'lift'))) {
      const far = village.far(link)!;
      const player = new SidePlayer(village, { x: link.x, y: link.y, map: link.map });
      player.update({ ...idle, use: true }, 1 / 60);
      hold(player, idle, 10);
      expect(player.mapPosition, link.id).toEqual({ x: far.x, y: far.y, map: far.map });
    }
  });
});
