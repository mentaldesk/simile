import { describe, expect, it } from 'vitest';
import { CollisionMap } from '../map';
import { FOOTPRINT, Player } from '../player';
import { gridDirection } from './controls';
import { project } from './projection';

const TILE = { width: 96, height: 48, px_per_metre_up: 53.443 };

function grid(...rows: string[]): CollisionMap {
  return new CollisionMap(
    rows[0].length,
    rows.length,
    rows.flatMap((row) => [...row].map((cell) => (cell === '#' ? 1 : 0))),
  );
}

const ROOM = grid(
  '#######', //
  '#.....#',
  '#.....#',
  '#.....#',
  '#.....#',
  '#.....#',
  '#######',
);

describe('gridDirection', () => {
  it('maps each arrow to the grid diagonal that looks that way on screen', () => {
    expect(gridDirection({ x: 0, y: -1 })).toEqual({ x: -1, y: -1 });
    expect(gridDirection({ x: 1, y: 0 })).toEqual({ x: 1, y: -1 });
    expect(gridDirection({ x: 0, y: 1 })).toEqual({ x: 1, y: 1 });
    expect(gridDirection({ x: -1, y: 0 })).toEqual({ x: -1, y: 1 });
    expect(gridDirection({ x: 0, y: 0 })).toEqual({ x: 0, y: 0 });
  });

  it('maps two arrows together to a grid axis', () => {
    expect(gridDirection({ x: 1, y: -1 })).toEqual({ x: 0, y: -2 });
    expect(gridDirection({ x: 1, y: 1 })).toEqual({ x: 2, y: 0 });
    expect(gridDirection({ x: -1, y: 1 })).toEqual({ x: 0, y: 2 });
    expect(gridDirection({ x: -1, y: -1 })).toEqual({ x: -2, y: 0 });
  });

  it('moves straight along the screen for a single arrow', () => {
    const screen = (direction: { x: number; y: number }) => project(TILE, gridDirection(direction));
    expect(screen({ x: 0, y: -1 })).toEqual({ x: 0, y: -48 });
    expect(screen({ x: 1, y: 0 })).toEqual({ x: 96, y: 0 });
  });
});

describe('the player under iso controls', () => {
  const walk = (from: { x: number; y: number }, arrows: { x: number; y: number }, seconds = 3) => {
    const player = new Player(from);
    for (let t = 0; t < seconds; t += 0.05) player.move(gridDirection(arrows), 0.05, ROOM);
    return player.position;
  };

  it('walks screen-up to the north-west corner, colliding in tiles', () => {
    const corner = { x: 1 - FOOTPRINT.left, y: 1 - FOOTPRINT.top, map: 'village' };
    expect(walk({ x: 3, y: 3 }, { x: 0, y: -1 })).toEqual(corner);
  });

  it('slides along a wall a diagonal step runs into', () => {
    const end = walk({ x: 1, y: 3 }, { x: 0, y: -1 }, 0.5);
    expect(end.x).toBe(1 - FOOTPRINT.left);
    expect(end.y).toBeLessThan(3);
  });

  it('walks screen-right to the north-east corner, then stays put', () => {
    const corner = { x: 6 - FOOTPRINT.right, y: 1 - FOOTPRINT.top, map: 'village' };
    expect(walk({ x: 3, y: 3 }, { x: 1, y: 0 })).toEqual(corner);
  });

  it('moves the same distance in tiles for one arrow or two', () => {
    const one = walk({ x: 3, y: 3 }, { x: 0, y: 1 }, 0.25);
    const two = walk({ x: 3, y: 3 }, { x: 1, y: 1 }, 0.25);
    expect(Math.hypot(one.x - 3, one.y - 3)).toBeCloseTo(Math.hypot(two.x - 3, two.y - 3));
  });
});
