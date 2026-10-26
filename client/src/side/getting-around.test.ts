import { describe, expect, it } from 'vitest';
import { village } from './content';
import { isStanding, type Cell, type SideMap } from './maps';
import { SidePlayer, spanEnd, type Controls, type MapPosition } from './player';
import { climbRuns } from './runs';
import { chosen, CLIMB_REACH, type Way } from './ways';

const idle: Controls = { x: 0, y: 0, use: false, run: false };
const EDGE = CLIMB_REACH - 0.1;
const OFFSETS = [-EDGE, -1, -0.5, 0, 0.5, 1, EDGE];
const maps = [...village.maps.values()];
const links = maps.flatMap(({ links }) => links);
const climbs = links.filter(({ kind }) => kind === 'stairs' || kind === 'ladder');

function hold(player: SidePlayer, controls: Controls, seconds: number): void {
  for (let t = 0; t < seconds; t += 1 / 60) player.update(controls, 1 / 60);
}

/** Holds up or down. Undefined if that key takes another way here. */
function climb(at: MapPosition, up: boolean, isIt: (way: Way) => boolean): SidePlayer | undefined {
  const player = new SidePlayer(village, at);
  const way = chosen(player.ways(), up ? 'up' : 'down');
  if (!way || !isIt(way)) return undefined;
  hold(player, { ...idle, y: up ? -1 : 1 }, 8);
  return player;
}

/** E pressed once, then a second of nothing. */
function pressE(at: MapPosition): SidePlayer {
  const player = new SidePlayer(village, at);
  const door = player.update({ ...idle, use: true }, 1 / 60);
  expect(door, `E at ${JSON.stringify(at)}`).toBeUndefined();
  hold(player, idle, 1);
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

  it('takes the player to its other end from anywhere in the tile either side, on up from its foot or down from its top', () => {
    for (const link of climbs) {
      let climbed = 0;
      const far = village.far(link)!;
      const up = village.map(far.map)!.floor > village.map(link.map)!.floor;
      const isIt = (way: Way) => 'link' in way && way.link === link;
      for (const x of around(village.map(link.map)!, link)) {
        const player = climb({ x, y: link.y, map: link.map }, up, isIt);
        if (!player) continue;
        climbed++;
        expect(player.mapPosition, `${link.id} from ${x} on ${link.map}`).toEqual({ x: far.x, y: far.y, map: far.map });
      }
      expect(climbed, link.id).toBeGreaterThan(0);
    }
  });

  it('does nothing on E from anywhere in reach of its end', () => {
    for (const link of climbs) {
      for (const x of around(village.map(link.map)!, link)) {
        const start = { x, y: link.y, map: link.map };
        const player = new SidePlayer(village, start);
        if (player.ways().some((way) => way.kind === 'door')) continue;
        const after = pressE(start);
        expect(after.climbing, `${link.id} from ${x}`).toBeUndefined();
        expect(after.mapPosition, `${link.id} from ${x}`).toEqual(start);
      }
    }
  });
});

describe('every flight and ladder on a street', () => {
  it('takes the player from either end to the other from anywhere in the tile beside it, and not on E', () => {
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
            const player = climb({ x, y: from.y, map: map.id }, up, isIt);
            if (!player) continue;
            climbed++;
            expect(player.climbing, `${map.id} from ${x}, ${from.y}`).toBeUndefined();
            expect(player.position).toEqual({ x: to.x, y: to.y });
            expect(pressE({ x, y: from.y, map: map.id }).position).toEqual({ x, y: from.y });
          }
          expect(climbed, `${map.id} from ${from.x}, ${from.y}`).toBeGreaterThan(0);
        }
      }
    }
  });
});

describe('every lift', () => {
  const lifts = links.filter(({ kind }) => kind === 'lift');
  const floorOf = (map: string) => village.map(map)!.floor;

  it('takes the player a floor up on up and a floor down on down, from either of its cells', () => {
    let rides = 0;
    for (const link of lifts) {
      const here = floorOf(link.map);
      for (const up of [true, false]) {
        const next = lifts
          .filter((other) => other.map === link.map && floorOf(other.to.map) - here === (up ? 1 : -1))
          .map((other) => village.far(other)!)[0];
        const player = new SidePlayer(village, { x: link.x, y: link.y, map: link.map });
        player.update({ ...idle, y: up ? -1 : 1 }, 1 / 60);
        hold(player, idle, 10);
        const expected = next ?? { x: link.x, y: link.y, map: link.map };
        expect(player.mapPosition, `${up ? 'up' : 'down'} from ${link.id} on ${link.map}`).toEqual({
          x: expected.x,
          y: expected.y,
          map: expected.map,
        });
        if (next) rides++;
      }
    }
    expect(rides).toBe(8);
  });

  it('does nothing on E from its cells', () => {
    for (const link of lifts) {
      const start = { x: link.x, y: link.y, map: link.map };
      expect(pressE(start).mapPosition).toEqual(start);
    }
  });
});

describe('every door', () => {
  const doors = links.filter(({ kind }) => kind === 'door');
  const jacked = (start: MapPosition) => Object.assign(new SidePlayer(village, start), { datajack: true });

  it('is taken on E from its cell, and never on up or down', () => {
    for (const door of doors) {
      const start = { x: door.x, y: door.y, map: door.map };
      expect(jacked(start).update({ ...idle, use: true }, 1 / 60), door.id).toBe(door);
      expect(jacked(start).update({ ...idle, y: -1 }, 1 / 60), door.id).toBeUndefined();
      expect(jacked(start).update({ ...idle, y: 1 }, 1 / 60), door.id).toBeUndefined();
    }
  });

  it("takes the lift down to the sewers only with the datajack, and back up without", () => {
    const [down] = doors.filter(({ id, map }) => id === 'metro_to_sewers' && map === 'metro');
    const [up] = doors.filter(({ id, map }) => id === 'metro_to_sewers' && map === 'sewers');
    const at = (door: typeof down) => ({ x: door.x, y: door.y, map: door.map });

    expect(new SidePlayer(village, at(down)).update({ ...idle, use: true }, 1 / 60)).toBeUndefined();
    expect(new SidePlayer(village, at(down)).ways()).toEqual([]);
    expect(jacked(at(down)).update({ ...idle, use: true }, 1 / 60)).toBe(down);
    expect(new SidePlayer(village, at(up)).update({ ...idle, use: true }, 1 / 60)).toBe(up);
  });

  it("isn't taken on up or down while E is free", () => {
    for (const door of doors) {
      for (const y of [-1, 1]) {
        const start = { x: door.x, y: door.y, map: door.map };
        const player = new SidePlayer(village, start);
        expect(player.update({ ...idle, y }, 1 / 60), door.id).toBeUndefined();
      }
    }
  });
});
