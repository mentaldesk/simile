import { describe, expect, it } from 'vitest';
import type { TiledMap } from '../world/map';
import { village } from './content';
import { BUFFER_SECONDS, COYOTE_SECONDS, JUMP_REACH, JUMP_RISE, JUMP_TABLE, JUMP_UP, landingRow } from './jump';
import positions from '../../../server/tests/street/positions.json';
import { CLIMB_KINDS, isSolid, isStanding, isWalkable, Village, type SideMap } from './maps';
import { RUN_PACE, SidePlayer, type Controls } from './player';
import { climbRuns, distanceTo, pointAlong } from './runs';
import { MAX_FRAME_SECONDS, PLAYER_SPEED } from '../world/tuning';

const DT = 1 / 60;
/** server/simile/street/moves.py's `ON_THE_WAY`. */
const ON_THE_WAY = 0.02;
const idle: Controls = { x: 0, y: 0, use: false, eTaken: false, run: false };
const press = (controls: Partial<Controls>): Controls => ({ ...idle, ...controls });

/** `#` is solid, `H` a ladder and anything else open air. */
function sketch(rows: string[]): SideMap {
  const [width, height] = [rows[0].length, rows.length];
  const at = (x: number, y: number) => rows[y]?.[x] ?? '#';
  const cells = (test: (x: number, y: number) => boolean) => {
    const out = new Uint8Array(width * height);
    for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) out[y * width + x] = Number(test(x, y));
    return out;
  };
  const climbable = cells((x, y) => at(x, y) === 'H').map((on) => (on ? CLIMB_KINDS.indexOf('ladder') + 1 : 0));
  return {
    id: 'test',
    kind: 'street',
    width,
    height,
    floor: 0,
    street: 'test',
    underground: false,
    offset: { x: 0, y: 0 },
    solid: cells((x, y) => at(x, y) === '#'),
    climbable,
    walkable: cells((x, y) => at(x, y) !== '#' && (at(x, y) === 'H' || at(x, y + 1) === '#')),
    buildings: [],
    furniture: [],
    locations: [],
    murals: [],
    links: [],
    interactables: [],
    spots: [],
    light: [],
    file: {} as TiledMap,
  };
}

/** Rooftops on row 5, so their standing row is 4, with gaps of one, two, three and five cells, over a lane on row 9. */
const ROOFS = sketch([
  '..............................',
  '..............................',
  '..............................',
  '..............................',
  '..............................',
  '#####.#####..#####...###.....#',
  '..............................',
  '..............................',
  '..............................',
  '##############################',
]);
const ROOF = 4;
const LANE = 8;

const on = (map: SideMap, x: number, y: number) => new SidePlayer(new Village([map]), { x, y, map: map.id });

/** Walks right from `x` to the edge `edge`, jumps there and keeps going right with Space held until it lands. */
function jumpRight(map: SideMap, x: number, edge: number, run = false, y = ROOF) {
  const player = on(map, x, y);
  for (let t = 0; t < 3 && player.position.x < edge; t += DT) player.update(press({ x: 1, run }), DT);
  player.update(press({ x: 1, run, jump: true, hold: true }), DT);
  expect(player.airborne).toBe(true);
  let highest = player.position.y;
  for (let t = 0; t < 3 && player.airborne; t += DT) {
    player.update(press({ x: 1, run, hold: true }), DT);
    highest = Math.min(highest, player.position.y);
  }
  expect(player.airborne).toBe(false);
  return { player, highest };
}

describe('jumping', () => {
  it('jumps a one-cell gap walking', () => {
    const { player } = jumpRight(ROOFS, 1, 4);
    expect(player.position.y).toBe(ROOF);
    expect(player.position.x).toBeGreaterThan(5.25);
  });

  it('jumps a two-cell gap walking, from the edge', () => {
    const { player } = jumpRight(ROOFS, 7, 10.5);
    expect(player.position.y).toBe(ROOF);
    expect(player.position.x).toBeGreaterThan(12.25);
  });

  it('jumps a three-cell gap running, which walking falls short of', () => {
    const walked = jumpRight(ROOFS, 14, 17).player;
    expect(walked.position.y).toBe(LANE);
    const ran = jumpRight(ROOFS, 14, 17, true).player;
    expect(ran.position).toMatchObject({ y: ROOF });
    expect(ran.position.x).toBeGreaterThan(20.25);
  });

  it('jumps as far as the neighbour rule says it can, and as high', () => {
    const gap = sketch([
      ...Array<string>(5).fill('....................'),
      `#####${'.'.repeat(JUMP_REACH - 1)}${'#'.repeat(15 - JUMP_REACH + 1)}`,
      '####################',
    ]);
    const { player } = jumpRight(gap, 1, 4.5, true, 4);
    expect(player.position).toMatchObject({ y: 4 });
    const step = sketch([...Array<string>(4).fill('......'), '...###', '......', '######']);
    const climber = on(step, 1, 5);
    climber.update(press({ x: 1, jump: true, hold: true }), DT);
    for (let t = 0; t < 2 && climber.airborne; t += DT) climber.update(press({ x: 1, hold: true }), DT);
    expect(climber.position.y).toBe(5 - JUMP_UP);
    expect(JUMP_RISE).toBeGreaterThan(JUMP_UP);
  });

  it("reaches as far as the server's table says the farthest jump does, and no further", () => {
    const open = '.'.repeat(30);
    const ledge = sketch([...Array<string>(6).fill(open), '######'.padEnd(30, '.'), open, open, open, '#'.repeat(30)]);
    const player = on(ledge, 0, 5);
    while (!player.airborne) player.update(press({ x: 1, run: true }), DT);
    for (let t = DT; t < COYOTE_SECONDS - DT / 2; t += DT) player.update(press({ x: 1, run: true }), DT);
    player.update(press({ x: 1, run: true, jump: true, hold: true }), DT);
    let farthest = 0;
    let highest = 5;
    while (player.position.y <= 5.5) {
      farthest = player.position.x;
      highest = Math.min(highest, player.position.y);
      player.update(press({ x: 1, run: true, hold: true }), DT);
    }
    expect(farthest - 5).toBeLessThanOrEqual(JUMP_TABLE.reach);
    expect(farthest - 5).toBeGreaterThan(JUMP_TABLE.reach - RUN_PACE * PLAYER_SPEED * MAX_FRAME_SECONDS - 0.1);
    expect(JUMP_TABLE.frame_seconds).toBe(MAX_FRAME_SECONDS);
    expect(5 - highest).toBeLessThanOrEqual(JUMP_TABLE.rise);
  });

  it.each([11.4, 14.6, 14.95])('falls from where a snapshot puts it in the air, %s rows down', (y) => {
    const player = on(village.map('high_street')!, 20, y);
    player.update(press({ x: 1 }), DT);
    expect(player.airborne).toBe(true);
    for (let t = 0; t < 2 && player.airborne; t += DT) player.update(idle, DT);
    expect(player.position.y).toBe(15);
  });

  it('goes further running than walking', () => {
    const open = sketch([...Array<string>(5).fill('....................'), '####################']);
    const distance = (run: boolean) => {
      const player = on(open, 2, 4);
      player.update(press({ x: 1, run }), 1);
      const from = player.position.x;
      player.update(press({ x: 1, run, jump: true, hold: true }), DT);
      while (player.airborne) player.update(press({ x: 1, run, hold: true }), DT);
      return player.position.x - from;
    };
    expect(distance(true)).toBeGreaterThan(1.8 * distance(false));
  });

  it('falls short into the lane below and lands safely, free to walk on', () => {
    const { player } = jumpRight(ROOFS, 20, 23, true);
    expect(player.position.y).toBe(LANE);
    expect(player.drawn.pose).toBe('landing');
    player.update(press({ x: -1 }), 0.5);
    expect(player.position.y).toBe(LANE);
    expect(player.drawn.pose).toBe('walking');
  });

  it('walks off a ledge and drops to the next floor with ground, from any height', () => {
    const tall = sketch(['......', '......', '......', '###...', ...Array<string>(8).fill('......'), '######']);
    const player = on(tall, 0, 2);
    for (let t = 0; t < 3 && player.position.y !== 11; t += DT) player.update(press({ x: 1 }), DT);
    expect(player.position.y).toBe(11);
    expect(player.airborne).toBe(false);
  });

  it('jumps higher with Space held than tapped', () => {
    const peak = (hold: boolean) => {
      const player = on(ROOFS, 2, ROOF);
      player.update(press({ jump: true, hold: true }), DT);
      let highest = ROOF;
      while (player.airborne) {
        player.update(press({ hold }), DT);
        highest = Math.min(highest, player.position.y);
      }
      return ROOF - highest;
    };
    expect(peak(true)).toBeCloseTo(JUMP_RISE, 1);
    expect(peak(true)).toBeGreaterThan(JUMP_UP);
    expect(peak(false)).toBeLessThan(JUMP_RISE / 2);
  });

  it('jumps for COYOTE_SECONDS after walking off a ledge, and not after', () => {
    const offEdge = (late: number) => {
      const player = on(ROOFS, 3, ROOF);
      while (!player.airborne) player.update(press({ x: 1 }), DT);
      for (let t = 0; t < late; t += DT) player.update(press({ x: 1 }), DT);
      const before = player.position.y;
      player.update(press({ x: 1, jump: true, hold: true }), DT);
      player.update(press({ x: 1, hold: true }), DT);
      return player.position.y - before;
    };
    expect(offEdge(COYOTE_SECONDS - 2 * DT)).toBeLessThan(0);
    expect(offEdge(COYOTE_SECONDS + 3 * DT)).toBeGreaterThan(0);
  });

  it('jumps again on landing when Space is pressed BUFFER_SECONDS before it, and not sooner', () => {
    const frames = (() => {
      const player = on(ROOFS, 2, ROOF);
      player.update(press({ jump: true, hold: true }), DT);
      let count = 1;
      while (player.airborne) {
        player.update(press({ hold: true }), DT);
        count++;
      }
      return count;
    })();
    const again = (early: number) => {
      const player = on(ROOFS, 2, ROOF);
      const pressAt = frames - Math.round(early / DT);
      player.update(press({ jump: true, hold: true }), DT);
      for (let frame = 1; frame < frames + 2; frame++) {
        player.update(press({ jump: frame === pressAt, hold: true }), DT);
      }
      return player.airborne;
    };
    expect(again(BUFFER_SECONDS - 2 * DT)).toBe(true);
    expect(again(BUFFER_SECONDS + 6 * DT)).toBe(false);
  });

  it("stops at walls and bumps its head on the room's ceiling", () => {
    const player = on(village.map('coffee_shop_floor_1')!, 1.5, 2);
    player.update(press({ jump: true, hold: true }), DT);
    let highest = 2;
    for (let t = 0; t < 2 && player.airborne; t += DT) {
      player.update(press({ x: -1, hold: true }), DT);
      highest = Math.min(highest, player.position.y);
    }
    expect(highest).toBeGreaterThan(0.6);
    expect(player.position).toEqual({ x: expect.closeTo(0.75, 2), y: 2 });
  });

  it("jumps on the High Street and lands where it took off, with no way to take while it's in the air", () => {
    const player = on(village.map('high_street')!, 10, 15);
    player.update(press({ jump: true, hold: true }), DT);
    player.update(press({ hold: true }), DT);
    expect(player.ways()).toEqual([]);
    expect(player.drawn.pose).toBe('jumping');
    for (let t = 0; t < 2 && player.airborne; t += DT) player.update(press({ hold: true }), DT);
    expect(player.position).toEqual({ x: 10, y: 15 });
  });

  it('keeps the camera at the height it jumped from, and its shadow on the ground under it', () => {
    const player = on(ROOFS, 2, ROOF);
    player.update(press({ jump: true, hold: true }), DT);
    for (let t = 0; t < 0.2; t += DT) player.update(press({ hold: true }), DT);
    expect(player.at.y).toBeLessThan(ROOF - 1);
    expect(player.steady.y).toBe(ROOF);
    expect(player.ground).toBe(ROOF);
    expect(landingRow(ROOFS, { x: 5, y: 1.5 })).toBe(LANE);
  });
});

/** On the way from a cell to the next along a row, or up or down a flight or a ladder. */
function between(map: SideMap, x: number, y: number): boolean {
  const row = Math.round(y);
  if (Math.abs(y - row) <= ON_THE_WAY && isWalkable(map, Math.floor(x), row) && isWalkable(map, Math.ceil(x), row)) {
    return true;
  }
  const at = { x: 0, y: 0 };
  return climbRuns(map).some(({ path }) => {
    pointAlong(path, distanceTo(path, { x, y }), at);
    return Math.hypot(at.x - x, at.y - y) <= ON_THE_WAY;
  });
}

/** A copy of server/simile/street/moves.py's `possible`, checked against the same table of cases. */
function possible(map: SideMap, x: number, y: number, last?: { x: number; y: number } | null): boolean {
  const [cx, cy] = [Math.floor(x + 0.5), Math.ceil(Math.round(y * 1e6) / 1e6)];
  if (isWalkable(map, cx, cy) || between(map, x, y)) return true;
  if (isSolid(map, cx, cy)) return false;
  let row = cy;
  while (row < map.height - 1 && !isSolid(map, cx, row + 1)) row++;
  if (!isStanding(map, cx, row)) return false;
  if (last && y > last.y && Math.abs(x - last.x) <= JUMP_TABLE.reach) return true;
  for (let sy = Math.ceil(y - 0.5); sy <= Math.floor(y + JUMP_TABLE.rise); sy++) {
    for (let sx = Math.floor(x - JUMP_TABLE.reach); sx <= Math.ceil(x + JUMP_TABLE.reach); sx++) {
      if (isStanding(map, sx, sy) && Math.abs(sx - x) <= JUMP_TABLE.reach) return true;
    }
  }
  return false;
}

describe("the server's rule", () => {
  it.each(positions.map((c) => [c.why, c.map, c.x, c.y, c.last, c.kept] as const))(
    '%s: %s at %s, %s after %o is kept: %s',
    (_, map, x, y, last, kept) => {
      expect(possible(village.map(map)!, x, y, last && { x: last[0], y: last[1] })).toBe(kept);
    },
  );
});

describe('on the rooftops', () => {
  const rooftops = village.map('rooftops')!;

  it.each([
    ['running and jumping along the roofs', { x: 5, y: 12 }, 1],
    ['jumping back the other way', { x: 38, y: 8 }, -1],
    ["walking off the clock house's roof", { x: 52, y: 4 }, 1],
  ])('sends the server only positions it keeps, %s', (_, start, way) => {
    for (const every of [1, 12]) {
      const player = on(rooftops, start.x, start.y);
      let last: { x: number; y: number } = { ...start };
      for (let frame = 0; frame < 60 * 10; frame++) {
        const jump = frame % 40 === 0;
        player.update(press({ x: way, run: way > 0 && start.y < 10, jump, hold: frame % 40 < 20 }), DT);
        if (frame % every) continue;
        const { x, y } = player.position;
        const where = `${x.toFixed(2)}, ${y.toFixed(2)} after ${last.x}, ${last.y}`;
        expect(possible(rooftops, x, y, last), where).toBe(true);
        last = { x, y };
      }
    }
  });

  it('sends nothing the server keeps from a sideways jump out of a fall', () => {
    expect(possible(rooftops, 56.2, 6.5, { x: 55.4, y: 4.6 })).toBe(true);
    expect(possible(rooftops, 44, 11, { x: 56.2, y: 6.5 })).toBe(false);
  });
});
