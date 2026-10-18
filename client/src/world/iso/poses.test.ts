import { describe, expect, it } from 'vitest';
import type { Facing, Pose } from '../../net';
import { characters } from '../assets';
import { tileOf } from '../map';
import { loadEveryMap } from '../maps.fixture';
import { ISO_FACING, POSES, seatAt, seatsOf, stillFor, stillFrame } from './poses';
import { facingFor, ISO_FACINGS, PIXEL_TEXTURE, type IsoFacing } from './sheets';
import { SITTING_NEARER } from './tuning';

type Atlas = { frames: Record<string, { frame: { w: number; h: number } }> };

const FACINGS: Facing[] = [
  'east',
  'south_east',
  'south',
  'south_west',
  'west',
  'north_west',
  'north',
  'north_east',
];
const STEPS: Record<Facing, { x: number; y: number }> = {
  east: { x: 1, y: 0 },
  south_east: { x: 1, y: 1 },
  south: { x: 0, y: 1 },
  south_west: { x: -1, y: 1 },
  west: { x: -1, y: 0 },
  north_west: { x: -1, y: -1 },
  north: { x: 0, y: -1 },
  north_east: { x: 1, y: -1 },
};
const SPOT_FACINGS: Facing[] = ['east', 'south', 'west', 'north'];

const maps = await loadEveryMap();

describe('ISO_FACING', () => {
  it.each(FACINGS)('turns %s the way a step that way faces', (facing) => {
    expect(ISO_FACING[facing]).toBe(facingFor(STEPS[facing], 'down'));
  });

  it('keeps the order the protocol and A1 share', () => {
    expect(FACINGS.map((facing) => ISO_FACING[facing])).toEqual(ISO_FACINGS);
  });
});

describe('stillFrame', () => {
  it('names the pose in a three-quarter view and the stand otherwise', () => {
    expect(stillFrame('down_left', 'sitting')).toBe('down_left-sitting');
    expect(stillFrame('up_right', 'working', true)).toBe('up_right-working-shift');
    expect(stillFrame('down', 'sitting')).toBe('down-1');
    expect(stillFrame('left')).toBe('left-1');
    expect(stillFrame('left', 'standing', true)).toBe('left-standing-shift');
  });

  it("is in every character's atlas for every pose a spot can face, and standing for all eight", () => {
    expect(characters.length).toBeGreaterThan(0);
    const names: string[] = ISO_FACINGS.flatMap((facing: IsoFacing) => [
      stillFrame(facing),
      stillFrame(facing, 'standing', true),
    ]);
    for (const facing of SPOT_FACINGS.map((f) => ISO_FACING[f])) {
      for (const pose of POSES) names.push(stillFrame(facing, pose), stillFrame(facing, pose, true));
    }
    for (const { key, atlas } of characters) {
      const { frames } = atlas as Atlas;
      for (const name of names) {
        expect(frames[name]?.frame, `${key} ${name}`).toMatchObject({
          w: PIXEL_TEXTURE.width,
          h: PIXEL_TEXTURE.height,
        });
      }
    }
  });
});

describe('stillFor', () => {
  const seat = { x: 0.6, y: 0, z: 0 };

  it.each<[Pose, Facing]>([
    ['sitting', 'east'],
    ['reading', 'north'],
    ['working', 'south'],
    ['looking', 'west'],
  ])('plays %s facing %s on its seat, whoever is near', (pose, facing) => {
    const still = stillFor({ pose, facing }, 'up', false, seat, { x: 1, y: 1 });
    const nearer = pose === 'sitting' ? SITTING_NEARER : 0;
    expect(still).toEqual({ frame: `${ISO_FACING[facing]}-${pose}`, facing: ISO_FACING[facing], seat, nearer });
  });

  it('shifts the weight of whoever is posed or standing', () => {
    expect(stillFor({ pose: 'sitting', facing: 'west' }, 'up', true, seat).frame).toBe('up_left-sitting-shift');
    expect(stillFor({ pose: 'standing', facing: 'west' }, 'up', true, undefined).frame).toBe(
      'up_left-standing-shift',
    );
  });

  it('stands facing the way the server says, or turns to whoever it should', () => {
    const body = { pose: 'standing' as const, facing: 'north' as const };
    expect(stillFor(body, 'down', false, undefined)).toEqual({
      frame: 'up_right-1',
      facing: 'up_right',
      seat: { x: 0, y: 0, z: 0 },
      nearer: 0,
    });
    expect(stillFor(body, 'down', false, undefined, { x: -2, y: 0 }).facing).toBe('up_left');
  });

  it('keeps the way they faced with nothing from the server, as for the player', () => {
    expect(stillFor({}, 'left', false, undefined).frame).toBe('left-1');
  });
});

describe('seatsOf', () => {
  it("reads where each spot's figure sits, and nothing elsewhere", () => {
    const seats = seatsOf(maps.coffee_shop);
    const west = seatAt(seats, tileOf({ x: 11, y: 7 }));
    const east = seatAt(seats, tileOf({ x: 13, y: 7 }));
    expect(west?.x).toBeGreaterThan(0.5);
    expect(east?.x).toBeLessThan(-0.5);
    expect(west?.y).toBe(0);
    expect(seatAt(seats, { x: 5, y: 9 })).toBeUndefined();
  });
});
