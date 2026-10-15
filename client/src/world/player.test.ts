import { describe, expect, it } from 'vitest';
import { village } from './assets';
import { CollisionMap, entryOf } from './map';
import { FOOTPRINT, Player, walk } from './player';
import { PLAYER_SPEED } from './tuning';

function grid(...rows: string[]): CollisionMap {
  return new CollisionMap(
    rows[0].length,
    rows.length,
    rows.flatMap((row) => [...row].map((cell) => (cell === '#' ? 1 : 0))),
  );
}

const ROOM = grid(
  '#####', //
  '#...#',
  '#...#',
  '#...#',
  '#####',
);

function push(map: CollisionMap, from: { x: number; y: number }, dx: number, dy: number, times = 20) {
  let position = from;
  for (let i = 0; i < times; i++) position = walk(map, position, dx, dy);
  return position;
}

describe('walk', () => {
  it('moves freely over open tiles', () => {
    expect(walk(ROOM, { x: 2, y: 2 }, 0.3, -0.2)).toEqual({ x: 2.3, y: 1.8 });
  });

  it('stops flush against a wall on each side', () => {
    expect(push(ROOM, { x: 2, y: 2 }, 0.2, 0).x).toBe(4 - FOOTPRINT.right);
    expect(push(ROOM, { x: 2, y: 2 }, -0.2, 0).x).toBe(1 - FOOTPRINT.left);
    expect(push(ROOM, { x: 2, y: 2 }, 0, 0.2).y).toBe(4 - FOOTPRINT.bottom);
    expect(push(ROOM, { x: 2, y: 2 }, 0, -0.2).y).toBe(1 - FOOTPRINT.top);
  });

  it('slides along a wall when moving diagonally into it', () => {
    const end = push(ROOM, { x: 2, y: 0.6 }, 0.1, -0.1, 5);
    expect(end.x).toBeCloseTo(2.5);
    expect(end.y).toBe(1 - FOOTPRINT.top);
  });

  it('never overlaps a blocked tile or reports one as its tile, whatever the moves', () => {
    const map = grid('.....', '.#...', '...#.', '.....');
    const overlaps = ({ x, y }: { x: number; y: number }) => {
      for (let row = Math.floor(y + FOOTPRINT.top); row < y + FOOTPRINT.bottom; row++) {
        for (let column = Math.floor(x + FOOTPRINT.left); column < x + FOOTPRINT.right; column++) {
          if (map.blocks(column, row)) return true;
        }
      }
      return false;
    };
    let seed = 7;
    const random = () => ((seed = (seed * 16807) % 2147483647) / 2147483647) * 1.8 - 0.9;
    let position = { x: 0, y: 0 };
    for (let i = 0; i < 2000; i++) {
      position = walk(map, position, random() / 3, random() / 3);
      expect(overlaps(position)).toBe(false);
      expect(map.blocks(Math.floor(position.x + 0.5), Math.floor(position.y + 0.5))).toBe(false);
    }
  });

  it('treats everything off the map as blocked', () => {
    const open = grid('...', '...');
    expect(push(open, { x: 1, y: 0 }, 0, -0.2).y).toBe(-FOOTPRINT.top);
    expect(push(open, { x: 1, y: 0 }, 0.2, 0).x).toBe(3 - FOOTPRINT.right);
  });
});

describe('the village', () => {
  const map = CollisionMap.of(village);

  it('has the square entry walkable and the coffee shop door blocked', () => {
    const square = entryOf(village, 'square')!;
    const cafe = entryOf(village, 'coffee_shop')!;
    expect(map.blocks(square.x, square.y)).toBe(false);
    expect(map.blocks(cafe.x, cafe.y)).toBe(false);
    expect(map.blocks(cafe.x, cafe.y - 1)).toBe(true);
  });

  it('stops the player at the coffee shop door, still on the tile in front of it', () => {
    const cafe = entryOf(village, 'coffee_shop')!;
    const stopped = push(map, cafe, 0, -0.2);
    expect(stopped.y).toBe(cafe.y - FOOTPRINT.top);
    expect([Math.floor(stopped.x + 0.5), Math.floor(stopped.y + 0.5)]).toEqual([cafe.x, cafe.y]);
  });
});

describe('Player', () => {
  it('walks at its speed in the direction of the keys, diagonals included', () => {
    const player = new Player({ x: 2, y: 2 });
    player.move({ x: 1, y: 1 }, 0.1, ROOM);
    expect(Math.hypot(player.position.x - 2, player.position.y - 2)).toBeCloseTo(PLAYER_SPEED * 0.1);
    expect(player.walking).toBe(true);
    expect(player.facing).toBe('down');
  });

  it('faces the way it was asked to go, and stands still against a wall', () => {
    const player = new Player({ x: 2, y: 1 - FOOTPRINT.top });
    player.move({ x: 0, y: -1 }, 0.1, ROOM);
    expect(player.facing).toBe('up');
    expect(player.walking).toBe(false);
  });

  it('faces the way it slides along a wall', () => {
    const player = new Player({ x: 2, y: 1 - FOOTPRINT.top });
    player.move({ x: 1, y: -1 }, 0.1, ROOM);
    expect(player.position.y).toBe(1 - FOOTPRINT.top);
    expect(player.walking).toBe(true);
    expect(player.facing).toBe('right');
  });

  it('stops walking when no key is down', () => {
    const player = new Player({ x: 2, y: 2 });
    player.move({ x: -1, y: 0 }, 0.1, ROOM);
    player.move({ x: 0, y: 0 }, 0.1, ROOM);
    expect(player.walking).toBe(false);
    expect(player.facing).toBe('left');
  });
});
