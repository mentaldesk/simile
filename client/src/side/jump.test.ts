import { describe, expect, it } from 'vitest';
import type { TiledMap } from '../world/map';
import { village } from './content';
import { BUFFER_SECONDS, COYOTE_SECONDS, JUMP_REACH, JUMP_RISE, JUMP_UP, landingRow } from './jump';
import { CLIMB_KINDS, Village, type SideMap } from './maps';
import { SidePlayer, type Controls } from './player';

const DT = 1 / 60;
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
      for (let frame = 1; frame < frames + 2; frame++) player.update(press({ jump: frame === pressAt, hold: true }), DT);
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
