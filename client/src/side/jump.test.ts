import { describe, expect, it } from 'vitest';
import type { Bionic, Body } from '../net';
import type { TiledMap } from '../world/map';
import { village } from './content';
import {
  BUFFER_SECONDS,
  COYOTE_SECONDS,
  JUMP_REACH,
  JUMP_RISE,
  JUMP_TABLE,
  JUMP_UP,
  GRAVITY,
  jumpOf,
  landingRow,
  LEGS_TABLES,
  type JumpTable,
} from './jump';
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
function possible(
  map: SideMap,
  x: number,
  y: number,
  last?: { x: number; y: number } | null,
  table: JumpTable = JUMP_TABLE,
): boolean {
  const [cx, cy] = [Math.floor(x + 0.5), Math.ceil(Math.round(y * 1e6) / 1e6)];
  if (isWalkable(map, cx, cy) || between(map, x, y)) return true;
  if (isSolid(map, cx, cy)) return false;
  let row = cy;
  while (row < map.height - 1 && !isSolid(map, cx, row + 1)) row++;
  if (!isStanding(map, cx, row)) return false;
  if (last && y > last.y && Math.abs(x - last.x) <= table.reach) return true;
  for (let sy = Math.ceil(y - 0.5); sy <= Math.floor(y + table.rise); sy++) {
    for (let sx = Math.floor(x - table.reach); sx <= Math.ceil(x + table.reach); sx++) {
      if (isStanding(map, sx, sy) && Math.abs(sx - x) <= table.reach) return true;
    }
  }
  return false;
}

describe("the server's rule", () => {
  it.each(positions.map((c) => [c.why, c.map, c.x, c.y, c.last, c.kept, ('legs' in c && c.legs) || ''] as const))(
    '%s: %s at %s, %s after %o is kept: %s',
    (_, map, x, y, last, kept, legs) => {
      const table = LEGS_TABLES.get(legs) ?? JUMP_TABLE;
      expect(possible(village.map(map)!, x, y, last && { x: last[0], y: last[1] }, table)).toBe(kept);
    },
  );
});

const whole: Body = {
  legs: 'present',
  vertebra: 'present',
  left_eye: 'present',
  right_eye: 'present',
  left_kidney: 'present',
  right_kidney: 'present',
};
const GRADES: Bionic[] = ['hydraulic_legs', 'spring_legs', 'sprint_legs', 'blade_legs', 'premium_legs'];
const tableOf = (legs?: Bionic) => jumpOf({ ...whole, legs: legs ?? 'present' });

/** On the legs' table, runs `way` from `from` (or walks) and jumps once past `at`, holding Space for `hold` frames; where it lands. */
function legsJump(legs: Bionic | undefined, from: { x: number; y: number }, way: 1 | -1, at: number, hold = 600, walk = false) {
  const table = tableOf(legs);
  const player = new SidePlayer(village, { ...from, map: 'metro' });
  player.rise = table.rise;
  player.runSpeed = table.run;
  const past = () => (way > 0 ? player.position.x >= at : player.position.x <= at);
  for (let t = 0; t < 5 && !past(); t += DT) player.update(press({ x: way, run: !walk }), DT);
  player.update(press({ x: way, run: !walk, jump: true, hold: true }), DT);
  let highest = player.position.y;
  for (let frame = 0; frame < 300 && player.airborne; frame++) {
    player.update(press({ x: way, run: !walk, hold: frame < hold }), DT);
    highest = Math.min(highest, player.position.y);
  }
  return { x: player.position.x, y: player.position.y, highest };
}

describe('on each grade of legs', () => {
  it('jumps as high and runs as fast as its table says, under the same gravity', () => {
    expect(tableOf()).toBe(JUMP_TABLE);
    expect(JUMP_TABLE.run).toBeCloseTo(RUN_PACE * PLAYER_SPEED, 9);
    for (const legs of GRADES) {
      const table = tableOf(legs);
      expect(table, legs).toBe(LEGS_TABLES.get(legs));
      expect((2 * table.rise) / table.rise_seconds ** 2).toBeCloseTo(GRAVITY, 6);
      expect(table.rise).toBeGreaterThan(table.rows);
      expect(15 - legsJump(legs, { x: 92, y: 15 }, 1, 0).highest, legs).toBeCloseTo(table.rise, 1);
      const player = new SidePlayer(village, { x: 30, y: 15, map: 'metro' });
      player.runSpeed = table.run;
      player.update(press({ x: 1, run: true }), 1);
      expect(player.speed, legs).toBeCloseTo(table.run, 6);
    }
  });

  it.each<[Bionic | undefined, number]>([
    [undefined, 15],
    ['sprint_legs', 15],
    ['blade_legs', 15],
    ['hydraulic_legs', 12],
    ['spring_legs', 12],
    ['premium_legs', 12],
  ])("runs and jumps onto the metro's high ledge only on legs that spring: %s lands on row %s", (legs, row) => {
    expect(legsJump(legs, { x: 101, y: 15 }, 1, 103).y).toBe(row);
  });

  it.each<[Bionic | undefined, boolean]>([
    [undefined, false],
    ['hydraulic_legs', false],
    ['blade_legs', false],
    ['spring_legs', true],
    ['premium_legs', true],
  ])('jumps from the tunnel wall up to the alcove only on the spring legs or better: %s, %s', (legs, reaches) => {
    expect(legsJump(legs, { x: 81, y: 10 }, 1, 82.5, 600, true).y === 5).toBe(reaches);
  });

  it.each<[Bionic, number]>([
    ['sprint_legs', 69],
    ['blade_legs', 69.5],
  ])("sprints across the gantry's gap under its roof on the %s, jumping as it passes %s", (legs, at) => {
    const landed = legsJump(legs, { x: 72, y: 8 }, -1, at);
    expect(landed.y).toBe(8);
    expect(landed.x).toBeLessThan(63.75);
  });

  it('crosses the gap on the premium legs with Space tapped, and bumps its head with it held', () => {
    expect(legsJump('premium_legs', { x: 72, y: 8 }, -1, 68.5, 4).y).toBe(8);
    expect(legsJump('premium_legs', { x: 72, y: 8 }, -1, 69).y).toBe(15);
  });

  it.each<[Bionic | undefined]>([[undefined], ['hydraulic_legs'], ['spring_legs']])(
    "never clears the gantry's gap on %s, however it jumps",
    (legs) => {
      for (const at of [70, 69.5, 69, 68.7, 68.5, 68.3]) {
        for (const hold of [0, 2, 4, 6, 8, 12, 20, 600]) {
          const landed = legsJump(legs, { x: 72, y: 8 }, -1, at, hold);
          expect(landed.y === 8 && landed.x < 64, `jumping at ${at}, holding ${hold}`).toBe(false);
        }
      }
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
