import { describe, expect, it, vi } from 'vitest';
import type { Position } from '../net';
import { mapIds } from './assets';
import { doorsOf, doorsOn, Doorways, type Arrival, type Door } from './doors';
import { CollisionMap } from './map';
import { loadEveryMap } from './maps.fixture';
import type { Direction } from './player';
import { DOOR_FADE_IN_SECONDS, DOOR_FADE_OUT_SECONDS } from './tuning';

const maps = await loadEveryMap();
const doors = mapIds.flatMap(doorsOn);
const NORTH = { x: 0, y: -1 };
const SOUTH = { x: 0, y: 1 };
const EAST = { x: 1, y: 0 };
const STILL = { x: 0, y: 0 };
const FRAME = 1 / 60;
const DOORSTEP = { x: 31, y: 11, map: 'village' };
const MAT = { x: 10, y: 13, map: 'coffee_shop' };

/** Runs frames at one spot until something arrives, or `seconds` pass. */
function hold(
  doorways: Doorways,
  position: Position,
  direction: Direction,
  seconds: number,
  ready: (map: string) => boolean = () => true,
): Arrival | undefined {
  for (let t = 0; t < seconds; t += FRAME) {
    const arrival = doorways.update(position, direction, FRAME, ready);
    if (arrival) return arrival;
  }
  return undefined;
}

describe('doorsOf', () => {
  it('pairs every door with its other end, which leads back', () => {
    expect(doors.length).toBeGreaterThan(0);
    for (const door of doors) {
      const end = doors.find(
        (other) => other.map === door.to.map && other.x === door.to.x && other.y === door.to.y,
      );
      expect(end, `${door.map} ${door.id}`).toBeDefined();
      expect(end!.to).toEqual({ map: door.map, x: door.x, y: door.y });
      expect(end!.id).toBe(door.id);
    }
  });

  it('leads from the Daily Grind’s doorstep to its mat, each facing away from the building', () => {
    const outside = doors.find((door) => door.map === 'village' && door.id === 'coffee_shop')!;
    const inside = doors.find((door) => door.map === 'coffee_shop')!;
    expect(outside).toMatchObject({ ...DOORSTEP, to: MAT, out: SOUTH });
    expect(inside).toMatchObject({ ...MAT, to: DOORSTEP, out: NORTH });
  });

  it('has a way out of every door onto open floor', () => {
    for (const door of doors) {
      const collision = CollisionMap.of(maps[door.map]);
      expect(collision.blocks(door.x, door.y)).toBe(false);
      expect(collision.blocks(door.x + door.out.x, door.y + door.out.y), `${door.map} ${door.id}`).toBe(false);
    }
  });
});

describe('Doorways', () => {
  it('takes a player who walks onto a door towards it through, fading to black and back', () => {
    const doorways = new Doorways();
    expect(hold(doorways, { x: 31, y: 12 }, NORTH, 0.1)).toBeUndefined();
    expect(doorways.update({ x: 31.2, y: 10.6 }, NORTH, FRAME, () => true)).toBeUndefined();
    expect(doorways.holding).toBe(true);
    doorways.update({ x: 31.2, y: 10.6 }, STILL, FRAME, () => true);
    expect(doorways.black).toBeCloseTo(FRAME / DOOR_FADE_OUT_SECONDS);

    const arrival = hold(doorways, { x: 31.2, y: 10.6 }, STILL, 1);
    expect(arrival).toEqual({ position: MAT, facing: NORTH });
    expect(doorways.black).toBe(1);
    expect(doorways.holding).toBe(false);

    hold(doorways, MAT, NORTH, DOOR_FADE_IN_SECONDS / 2);
    expect(doorways.black).toBeGreaterThan(0.3);
    expect(doorways.black).toBeLessThan(0.7);
    hold(doorways, MAT, NORTH, DOOR_FADE_IN_SECONDS);
    expect(doorways.black).toBe(0);
  });

  it('starts loading the other side at once, and waits at black until it can be drawn', () => {
    const doorways = new Doorways();
    let loaded = false;
    const ready = vi.fn(() => loaded);
    hold(doorways, { x: 31, y: 12 }, NORTH, 0.1, ready);
    doorways.update(DOORSTEP, NORTH, FRAME, ready);
    expect(ready).toHaveBeenCalledWith('coffee_shop');

    expect(hold(doorways, DOORSTEP, STILL, 2, ready)).toBeUndefined();
    expect(doorways.black).toBe(1);
    expect(doorways.holding).toBe(true);
    loaded = true;
    expect(hold(doorways, DOORSTEP, STILL, FRAME, ready)?.position).toEqual(MAT);
  });

  it('doesn’t send a player back through the door they arrive on until they step off it', () => {
    const doorways = new Doorways();
    hold(doorways, { x: 31, y: 12 }, NORTH, 0.1);
    hold(doorways, DOORSTEP, NORTH, 1);

    expect(hold(doorways, MAT, SOUTH, 2)).toBeUndefined();
    expect(doorways.black).toBe(0);

    hold(doorways, { x: 10, y: 12.4, map: 'coffee_shop' }, NORTH, 0.1);
    expect(hold(doorways, MAT, SOUTH, 1)).toEqual({ position: DOORSTEP, facing: SOUTH });
  });

  it('lets a player walk past a doorstep, or stand on it, without going in', () => {
    const doorways = new Doorways();
    hold(doorways, { x: 29, y: 11 }, EAST, 0.1);
    for (let x = 29; x < 33; x += 0.05) doorways.update({ x, y: 11 }, EAST, FRAME, () => true);
    expect(doorways.holding).toBe(false);
    expect(hold(doorways, DOORSTEP, STILL, 1)).toBeUndefined();
    expect(hold(doorways, DOORSTEP, SOUTH, 1)).toBeUndefined();
    expect(doorways.black).toBe(0);
  });

  it('needs a player who starts on a door to step off it first', () => {
    const doorways = new Doorways();
    expect(hold(doorways, DOORSTEP, NORTH, 1)).toBeUndefined();
    hold(doorways, { x: 31, y: 11.6 }, SOUTH, 0.1);
    expect(hold(doorways, DOORSTEP, NORTH, 1)?.position).toEqual(MAT);
  });

  it('finds the door at a tile on its own map only', () => {
    const doorways = new Doorways();
    expect(doorways.doorAt('village', { x: 31, y: 11 })?.to.map).toBe('coffee_shop');
    expect(doorways.doorAt('coffee_shop', { x: 31, y: 11 })).toBeUndefined();
    expect(doorways.doorAt('coffee_shop', { x: 10, y: 13 })?.to.map).toBe('village');
  });
});

it('lists the doors of a map built in code', () => {
  const door: Door[] = doorsOf('village', {
    width: 3,
    height: 3,
    tilewidth: 16,
    tileheight: 16,
    layers: [
      {
        name: 'doors',
        type: 'objectgroup',
        objects: [
          {
            name: 'shop',
            type: 'door',
            x: 16,
            y: 16,
            properties: [
              { name: 'side', type: 'string', value: 'outside' },
              { name: 'to_map', type: 'string', value: 'shop' },
              { name: 'to_x', type: 'int', value: 4 },
              { name: 'to_y', type: 'int', value: 5 },
            ],
          },
        ],
      },
    ],
  });
  expect(door).toEqual([{ id: 'shop', map: 'village', x: 1, y: 1, to: { map: 'shop', x: 4, y: 5 }, out: SOUTH }]);
});
