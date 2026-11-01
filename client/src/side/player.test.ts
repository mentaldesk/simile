import { describe, expect, it } from 'vitest';
import { MoveThrottle } from '../world/throttle';
import { MAX_FRAME_SECONDS, PLAYER_SPEED } from '../world/tuning';
import { village } from './content';
import { TILE_M } from './layout';
import { RIDE_SPEED, RUN_CYCLE_M, WALK_CYCLE_M } from './motion';
import { PLAYER_CLIMB, RUN_BLEND_SECONDS, RUN_PACE, SidePlayer, type Controls, type MapPosition } from './player';

const idle: Controls = { x: 0, y: 0, use: false, run: false };
const press = (controls: Partial<Controls>): Controls => ({ ...idle, ...controls });
const RUN_SPEED = RUN_PACE * PLAYER_SPEED;

function hold(player: SidePlayer, controls: Controls, seconds: number, dt = 1 / 60) {
  let door;
  for (let t = 0; t < seconds - 1e-9; t += dt) door ??= player.update(controls, dt);
  return door;
}

const at = (position: MapPosition) => new SidePlayer(village, position);

describe('walking', () => {
  it('walks left and right along the street at its speed, facing the way it goes', () => {
    const player = at({ x: 10, y: 15, map: 'high_street' });
    hold(player, press({ x: 1 }), 1);
    expect(player.position.x).toBeCloseTo(10 + PLAYER_SPEED, 1);
    expect(player.drawn).toMatchObject({ pose: 'walking', facing: 'east', run: 0 });
    hold(player, press({ x: -1 }), 0.1);
    expect(player.facing).toBe('west');
    player.update(idle, 1 / 60);
    expect(player.drawn.pose).toBe('standing');
  });

  it('steps through the walk cycle a stride at a time', () => {
    const player = at({ x: 10, y: 15, map: 'high_street' });
    hold(player, press({ x: 1 }), 1);
    expect(player.drawn.phase).toBeCloseTo(((player.position.x - 10) * TILE_M) / WALK_CYCLE_M, 6);
  });

  it('stops at the end of the street and at the top of stairs', () => {
    const player = at({ x: 2, y: 15, map: 'high_street' });
    hold(player, press({ x: -1 }), 2);
    expect(player.position.x).toBe(0);
    const banyan = at({ x: 50, y: 15, map: 'banyan_row' });
    hold(banyan, press({ x: 1 }), 3);
    expect(banyan.position.x).toBe(53);
  });

  it('stays in the room, between its walls', () => {
    const player = at({ x: 3, y: 2, map: 'house_1_floor_0' });
    hold(player, press({ x: 1 }), 3);
    expect(player.position.x).toBe(5);
    expect(player.at).toEqual({ x: 7, y: 15 });
  });

  it('turns its back or its front on up and down where there is nothing to take', () => {
    const player = at({ x: 10, y: 15, map: 'high_street' });
    player.update(press({ y: -1 }), 1 / 60);
    expect(player.drawn.facing).toBe('north');
    player.update(press({ y: 1 }), 1 / 60);
    expect(player.drawn.facing).toBe('south');
  });
});

describe('running', () => {
  it('runs at RUN_PACE times walking speed while Shift is held, on a street and on a floor', () => {
    for (const start of [
      { x: 10, y: 15, map: 'high_street' },
      { x: 1, y: 2, map: 'gallery_floor_0' },
    ]) {
      const player = at(start);
      hold(player, press({ x: 1, run: true }), RUN_BLEND_SECONDS);
      const from = player.position.x;
      hold(player, press({ x: 1, run: true }), 1);
      expect(player.position.x - from, start.map).toBeCloseTo(RUN_SPEED, 1);
      expect(player.drawn).toMatchObject({ pose: 'walking', run: 1 });
    }
  });

  it('turns a walk into a run over RUN_BLEND_SECONDS, and back once Shift is let go', () => {
    const player = at({ x: 10, y: 15, map: 'high_street' });
    hold(player, press({ x: 1 }), 0.5);
    player.update(press({ x: 1, run: true }), RUN_BLEND_SECONDS / 2);
    expect(player.drawn.run).toBeCloseTo(0.5, 6);
    expect(player.speed).toBeCloseTo(PLAYER_SPEED * (1 + RUN_PACE) / 2, 6);
    hold(player, press({ x: 1, run: true }), RUN_BLEND_SECONDS);
    expect(player.drawn.run).toBe(1);
    player.update(press({ x: 1 }), RUN_BLEND_SECONDS / 4);
    expect(player.drawn.run).toBeCloseTo(0.75, 6);
    hold(player, press({ x: 1 }), RUN_BLEND_SECONDS);
    expect(player.drawn.run).toBe(0);
    expect(player.speed).toBe(PLAYER_SPEED);
  });

  it('takes longer strides running, so the cycle turns slower than the speed rises', () => {
    const player = at({ x: 10, y: 15, map: 'high_street' });
    hold(player, press({ x: 1, run: true }), RUN_BLEND_SECONDS);
    const [x, phase] = [player.position.x, player.drawn.phase];
    hold(player, press({ x: 1, run: true }), 0.5);
    expect(player.drawn.phase - phase).toBeCloseTo(((player.position.x - x) * TILE_M) / RUN_CYCLE_M, 6);
    expect(RUN_CYCLE_M).toBeGreaterThan(WALK_CYCLE_M);
    expect(RUN_CYCLE_M).toBeLessThan(RUN_PACE * WALK_CYCLE_M);
  });

  it('stands still, not running, with Shift held and nothing else', () => {
    const player = at({ x: 10, y: 15, map: 'high_street' });
    hold(player, press({ run: true }), 1);
    expect(player.position.x).toBe(10);
    expect(player.drawn).toMatchObject({ pose: 'standing', run: 0 });
  });

  it("doesn't climb stairs or ladders, or ride the lift, any faster", () => {
    const climbTime = (start: MapPosition, y: -1 | 1, run: boolean) => {
      const player = at(start);
      let frames = 0;
      while (player.map === start.map && frames < 1000) {
        player.update(press({ y, run }), 1 / 60);
        frames++;
      }
      return frames;
    };
    for (const [start, y] of [
      [{ x: 15, y: 2, map: 'coffee_shop_floor_0' }, -1],
      [{ x: 6, y: 2, map: 'maker_space_floor_1' }, -1],
      [{ x: 16, y: 2, map: 'gallery_floor_0' }, -1],
    ] as const) {
      expect(climbTime(start, y, true), start.map).toBe(climbTime(start, y, false));
    }
  });

  it('never moves faster than RUN_PACE times walking speed, nor reports moves that do', () => {
    const player = at({ x: 2, y: 15, map: 'high_street' });
    const throttle = new MoveThrottle();
    let last = { ...player.mapPosition };
    let sent: { x: number; at: number } | undefined;
    let now = 0;
    const steps = [1 / 60, 1 / 30, MAX_FRAME_SECONDS, 1 / 144];
    for (let i = 0; i < 1500; i++) {
      const dt = steps[i % steps.length];
      now += dt;
      player.update(press({ x: i % 400 < 380 ? 1 : -1, run: i % 97 > 20 }), dt);
      const position = player.mapPosition;
      expect(Math.abs(position.x - last.x)).toBeLessThanOrEqual(RUN_SPEED * dt + 1e-9);
      last = { ...position };
      const move = throttle.next(position, now);
      if (!move) continue;
      if (sent) expect(Math.abs(move.x - sent.x)).toBeLessThanOrEqual(RUN_SPEED * (now - sent.at) + 0.01);
      sent = { x: move.x, at: now };
    }
  });
});

describe('doors', () => {
  it('goes through a door on E in front of it, not on up or walking past', () => {
    const player = at({ x: 41, y: 15, map: 'high_street' });
    expect(hold(player, press({ x: 1 }), 1)).toBeUndefined();
    expect(hold(at({ x: 43, y: 15, map: 'high_street' }), press({ y: -1 }), 0.5)).toBeUndefined();
    expect(at({ x: 43, y: 15, map: 'high_street' }).update(press({ use: true }), 1 / 60)?.to.map).toBe(
      'coffee_shop_floor_0',
    );
  });


  it('leaves a building by its front door on E, and not on down', () => {
    const player = at({ x: 18, y: 2, map: 'coffee_shop_floor_0' });
    expect(hold(player, press({ y: 1 }), 0.5)).toBeUndefined();
    expect(player.update(press({ use: true }), 1 / 60)?.to).toEqual({ map: 'high_street', x: 43, y: 15 });
  });

  it("doesn't go in through a front door or a street door on down", () => {
    for (const x of [43, 46]) {
      const player = at({ x, y: 15, map: 'high_street' });
      expect(hold(player, press({ y: 1 }), 0.5)).toBeUndefined();
      expect(player.map).toBe('high_street');
    }
  });

  it('takes the door on E and the stairs on up where they are side by side', () => {
    expect(at({ x: 2, y: 2, map: 'noodle_bar_floor_0' }).update(press({ use: true }), 1 / 60)?.to.map).toBe(
      'high_street',
    );
    const player = at({ x: 2, y: 2, map: 'noodle_bar_floor_0' });
    hold(player, press({ y: -1 }), 0.5);
    expect(player.climbing).toBe('stairs');
    hold(player, press({ y: -1 }), 4);
    expect(player.mapPosition).toEqual({ x: 7, y: 2, map: 'noodle_bar_floor_1' });
  });
});

describe('stairs and ladders between floors', () => {
  it('starts on up at the foot, then climbs while up is held, stopping anywhere', () => {
    const player = at({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
    player.update(press({ y: -1 }), 1 / 60);
    expect(player.climbing).toBe('stairs');
    hold(player, press({ y: -1 }), 1);
    const partway = { ...player.at };
    expect(partway.x).toBeGreaterThan(40);
    expect(partway.y).toBeLessThan(15);
    expect(player.drawn).toMatchObject({ pose: 'climbing', on: 'stairs', facing: 'east' });
    expect(player.mapPosition).toEqual({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
    hold(player, idle, 1);
    expect(player.at).toEqual(partway);
    hold(player, press({ y: -1 }), 5 / PLAYER_CLIMB.stairs);
    expect(player.climbing).toBeUndefined();
    expect(player.mapPosition).toEqual({ x: 18, y: 2, map: 'coffee_shop_floor_1' });
  });

  it('climbs down from the top on down, once up is let go', () => {
    const player = at({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
    hold(player, press({ y: -1 }), 0.5 + 5 / PLAYER_CLIMB.stairs);
    expect(player.mapPosition).toEqual({ x: 18, y: 2, map: 'coffee_shop_floor_1' });
    hold(player, press({ y: 1 }), 0.5);
    expect(player.climbing).toBeUndefined();
    player.update(idle, 1 / 60);
    hold(player, press({ y: 1 }), 0.5 + 5 / PLAYER_CLIMB.stairs);
    expect(player.mapPosition).toEqual({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
  });

  it('steps onto the end from anywhere in the tile either side, then climbs', () => {
    for (const x of [13.6, 14, 14.4, 15.7, 16, 16.4]) {
      const player = at({ x, y: 2, map: 'coffee_shop_floor_0' });
      player.update(press({ y: -1 }), 1 / 60);
      expect(player.drawn.pose).toBe('walking');
      hold(player, press({ y: -1 }), 1 + 5 / PLAYER_CLIMB.stairs);
      expect(player.mapPosition, `from ${x}`).toEqual({ x: 18, y: 2, map: 'coffee_shop_floor_1' });
    }
    const far = at({ x: 13.4, y: 2, map: 'coffee_shop_floor_0' });
    hold(far, press({ y: -1 }), 1);
    expect(far.climbing).toBeUndefined();
    expect(far.position.x).toBe(13.4);
  });

  it('steps onto the top from the tile beside it on down, then climbs down', () => {
    const player = at({ x: 16.6, y: 2, map: 'coffee_shop_floor_1' });
    hold(player, press({ y: 1 }), 1 + 5 / PLAYER_CLIMB.stairs);
    expect(player.mapPosition).toEqual({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
  });

  it('does nothing on E at the foot or the top of stairs or a ladder', () => {
    for (const start of [
      { x: 15, y: 2, map: 'coffee_shop_floor_0' },
      { x: 16, y: 2, map: 'coffee_shop_floor_0' },
      { x: 18, y: 2, map: 'coffee_shop_floor_1' },
      { x: 6, y: 2, map: 'maker_space_floor_1' },
      { x: 6, y: 2, map: 'maker_space_floor_2' },
      { x: 53, y: 15, map: 'banyan_row' },
      { x: 45, y: 15, map: 'lychee_lane' },
    ]) {
      const player = at(start);
      expect(player.update(press({ use: true }), 1 / 60), start.map).toBeUndefined();
      hold(player, idle, 1);
      expect(player.climbing, start.map).toBeUndefined();
      expect(player.mapPosition, start.map).toEqual(start);
      expect(player.drawn.pose, start.map).toBe('standing');
    }
  });

  it('lets go of the stairs it was stepping to when turned back', () => {
    const player = at({ x: 16, y: 2, map: 'coffee_shop_floor_0' });
    player.update(press({ y: -1 }), 1 / 60);
    hold(player, press({ x: 1 }), 0.5);
    expect(player.climbing).toBeUndefined();
    expect(player.position.x).toBeGreaterThan(16);
  });

  it("doesn't climb on from the top while up is still held after arriving", () => {
    const player = at({ x: 2, y: 2, map: 'maker_space_floor_0' });
    hold(player, press({ y: -1 }), 0.5 + 5 / PLAYER_CLIMB.stairs);
    expect(player.mapPosition).toEqual({ x: 5, y: 2, map: 'maker_space_floor_1' });
    hold(player, press({ y: -1 }), 1);
    expect(player.climbing).toBeUndefined();
    player.update(idle, 1 / 60);
    hold(player, press({ y: -1 }), 1);
    expect(player.climbing).toBe('ladder');
  });

  it('climbs with left and right along the flight too, and steps back off at the foot', () => {
    const player = at({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
    player.update(press({ y: -1 }), 1 / 60);
    hold(player, press({ x: 1 }), 0.5);
    expect(player.at.y).toBeLessThan(15);
    hold(player, press({ x: -1 }), 2);
    expect(player.climbing).toBeUndefined();
    expect(player.mapPosition).toMatchObject({ y: 2, map: 'coffee_shop_floor_0' });
    expect(player.position.x).toBeLessThan(15);
  });

  it('keeps climbing stairs, or a ladder between floors, on Space', () => {
    for (const [start, kind] of [
      [{ x: 15, y: 2, map: 'coffee_shop_floor_0' }, 'stairs'],
      [{ x: 6, y: 2, map: 'maker_space_floor_1' }, 'ladder'],
    ] as const) {
      const player = at(start);
      hold(player, press({ y: -1 }), 1);
      player.update(press({ y: -1, jump: true, hold: true }), 1 / 60);
      expect(player.climbing, start.map).toBe(kind);
      expect(player.airborne, start.map).toBe(false);
    }
  });

  it('climbs a ladder from the back', () => {
    const player = at({ x: 6, y: 2, map: 'maker_space_floor_1' });
    hold(player, press({ y: -1 }), 1);
    expect(player.drawn).toMatchObject({ pose: 'climbing', on: 'ladder', facing: 'north' });
    expect(player.at.x).toBe(8);
    hold(player, press({ y: -1 }), 3);
    expect(player.map).toBe('maker_space_floor_2');
  });
});

describe('the lift', () => {
  it('rides a floor up on up and a floor down on down, all the way once started', () => {
    const player = at({ x: 16, y: 2, map: 'gallery_floor_0' });
    player.update(press({ y: -1 }), 1 / 60);
    hold(player, idle, 1 / RIDE_SPEED);
    expect(player.drawn).toMatchObject({ pose: 'riding', facing: 'south' });
    hold(player, idle, 5 / RIDE_SPEED);
    expect(player.mapPosition).toEqual({ x: 16, y: 2, map: 'gallery_floor_1' });
    player.update(press({ y: -1 }), 1 / 60);
    hold(player, idle, 6 / RIDE_SPEED);
    expect(player.mapPosition).toEqual({ x: 15, y: 2, map: 'gallery_floor_2' });
    player.update(press({ y: 1 }), 1 / 60);
    hold(player, idle, 6 / RIDE_SPEED);
    expect(player.mapPosition).toEqual({ x: 15, y: 2, map: 'gallery_floor_1' });
    player.update(press({ y: 1 }), 1 / 60);
    hold(player, idle, 6 / RIDE_SPEED);
    expect(player.mapPosition).toEqual({ x: 16, y: 2, map: 'gallery_floor_0' });
  });

  it('goes to the next floor from either of its cells', () => {
    const player = at({ x: 15, y: 2, map: 'gallery_floor_0' });
    player.update(press({ y: -1 }), 1 / 60);
    hold(player, idle, 8 / RIDE_SPEED);
    expect(player.mapPosition).toEqual({ x: 16, y: 2, map: 'gallery_floor_1' });
  });

  it("doesn't ride on E, or on down from the ground floor", () => {
    for (const controls of [press({ use: true }), press({ y: 1 })]) {
      const player = at({ x: 16, y: 2, map: 'gallery_floor_0' });
      hold(player, controls, 1);
      expect(player.climbing).toBeUndefined();
      expect(player.mapPosition).toEqual({ x: 16, y: 2, map: 'gallery_floor_0' });
    }
  });
});

describe('stairs and ladders on a street', () => {
  it("takes Banyan Row's stairs down to the river on down, then along with right", () => {
    const player = at({ x: 53, y: 15, map: 'banyan_row' });
    player.update(press({ y: 1 }), 1 / 60);
    hold(player, press({ x: 1 }), 0.5);
    expect(player.drawn).toMatchObject({ pose: 'climbing', on: 'stairs', facing: 'east' });
    hold(player, press({ x: 1 }), (3 * Math.SQRT2 - 0.5 * 2) / 2 - 0.05);
    expect(player.climbing).toBe('stairs');
    hold(player, press({ x: 1 }), 0.2);
    expect(player.climbing).toBeUndefined();
    expect(player.position.y).toBe(18);
    hold(player, press({ x: 1 }), 1);
    expect(player.position.x).toBeGreaterThan(57);
  });

  it('climbs the park ladder, steps off onto the lookout and walks off its end to the path', () => {
    const player = at({ x: 45, y: 15, map: 'lychee_lane' });
    hold(player, press({ y: -1 }), 1);
    expect(player.position.x).toBe(45);
    expect(player.position.y).toBeLessThan(15);
    hold(player, press({ y: -1 }), 4);
    expect(player.position).toEqual({ x: 46, y: 12 });
    expect(player.climbing).toBeUndefined();
    expect(player.drawn.pose).toBe('standing');
    hold(player, press({ x: 1 }), 0.7);
    expect(player.position.y).toBe(12);
    expect(player.position.x).toBeGreaterThan(47.5);
    hold(player, press({ x: 1 }), 1);
    expect(player.position.y).toBe(15);
    expect(player.airborne).toBe(false);
  });

  it('gets back on the ladder from the lookout on down', () => {
    const player = at({ x: 46, y: 12, map: 'lychee_lane' });
    hold(player, press({ y: 1 }), 6);
    expect(player.position).toEqual({ x: 45, y: 15 });
  });
});
