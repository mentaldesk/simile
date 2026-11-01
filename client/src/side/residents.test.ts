import { describe, expect, it } from 'vitest';
import type { Entity, EntityMovedMessage, Facing, Pose, Position } from '../net';
import { WALKING_SPEED } from '../world/tuning';
import { village } from './content';
import { CLIMB_SPEED, RIDE_SPEED, Walker, WALK_CYCLE_M } from './motion';
import { LIE_SECONDS } from './poses';
import { server } from '../net';
import { Residents, sideResidents } from './residents';

const odalys: Entity = {
  id: 'odalys',
  kind: 'npc',
  name: 'Odalys',
  position: { x: 10, y: 15, map: 'high_street' },
  pose: 'standing',
  facing: 'south',
};

function residents(entity: Entity = odalys): Residents {
  const all = new Residents();
  all.village = village;
  all.reset([entity, { id: 'player', kind: 'player', name: 'You', position: { x: 0, y: 15, map: 'high_street' } }]);
  return all;
}

const moved = (position: Position, pose: Pose = 'walking', facing: Facing = 'east'): EntityMovedMessage => ({
  type: 'entity_moved',
  entity_id: 'odalys',
  position,
  pose,
  facing,
});

function run(all: Residents, seconds: number, step = 1 / 60): void {
  for (let t = 0; t < seconds; t += step) all.update(step);
}

describe('the walker', () => {
  it('walks through each position at its speed, and keeps count', () => {
    const walker = new Walker({ x: 0, y: 0 }, 2);
    walker.moveTo({ x: 1, y: 0 });
    walker.moveTo({ x: 1, y: 0.4 });
    walker.update(0.5);
    expect(walker.position).toEqual({ x: 1, y: 0 });
    walker.update(0.1);
    expect(walker.position.y).toBeCloseTo(0.2);
    expect(walker.travelled).toBeCloseTo(1.2);
    expect(walker.moving).toBe(true);
  });

  it('places rather than walks across a gap', () => {
    const walker = new Walker({ x: 0, y: 0 }, 2);
    walker.moveTo({ x: 5, y: 0 });
    expect(walker.position).toEqual({ x: 5, y: 0 });
    expect(walker.arrived).toBe(true);
  });

  it("is placed rather than falling ever further behind while it isn't drawn", () => {
    const walker = new Walker({ x: 0, y: 0 }, 2);
    for (let x = 1; x <= 40; x++) walker.moveTo({ x: x * 0.5, y: 0 });
    expect(walker.position.x).toBeGreaterThan(0);
    walker.update(100);
    expect(walker.position.x).toBe(20);
  });

  it('remembers the way it last went along the street', () => {
    const walker = new Walker({ x: 3, y: 0 }, 2);
    walker.moveTo({ x: 2, y: 0 });
    walker.update(1);
    expect(walker.heading).toBe(-1);
  });
});

describe('residents on the street', () => {
  it('ignores the player and anyone it was never told of', () => {
    const all = residents();
    expect([...all.all.keys()]).toEqual(['odalys']);
    all.move({ ...moved({ x: 1, y: 15, map: 'high_street' }), entity_id: 'nobody' });
  });

  it('walks by phase, facing the way it goes', () => {
    const all = residents();
    all.move(moved({ x: 11, y: 15, map: 'high_street' }, 'walking', 'east'));
    all.update(0.3);
    const odalys = all.all.get('odalys')!;
    expect(odalys.drawn).toMatchObject({ pose: 'walking', facing: 'east' });
    expect(odalys.drawn.phase).toBeCloseTo((0.3 * WALKING_SPEED * 1.1) / WALK_CYCLE_M);
    all.move(moved({ x: 10, y: 15, map: 'high_street' }, 'walking', 'west'));
    run(all, 2);
    expect(odalys.at).toEqual({ x: 10, y: 15 });
    expect(odalys.drawn).toMatchObject({ pose: 'standing', facing: 'west' });
  });

  it("settles into the server's pose and facing", () => {
    const all = residents();
    all.move(moved({ x: 10, y: 15, map: 'high_street' }, 'looking', 'north'));
    run(all, 0.5);
    expect(all.all.get('odalys')!.drawn).toMatchObject({ pose: 'looking', facing: 'north', seated: false });
  });

  it('sits to work at a desk and stands to work elsewhere', () => {
    const desk: Entity = { ...odalys, position: { x: 1, y: 2, map: 'maker_space_floor_1' }, pose: 'working', facing: 'north' };
    const all = residents(desk);
    all.update(0.1);
    const odalysAt = all.all.get('odalys')!;
    expect(odalysAt.drawn).toMatchObject({ pose: 'working', seated: true });
    expect(odalysAt.at).toEqual({ x: 3, y: 11 });
    all.move(moved({ x: 6, y: 2, map: 'maker_space_floor_1' }, 'working', 'north'));
    all.update(0.1);
    all.move(moved({ x: 6, y: 2, map: 'maker_space_floor_1' }, 'working', 'north'));
    run(all, 3);
    expect(odalysAt.drawn.seated).toBe(false);
  });

  it("climbs Banyan Row's stairs, side on", () => {
    const all = residents({ ...odalys, position: { x: 53, y: 15, map: 'banyan_row' } });
    all.move(moved({ x: 54, y: 16, map: 'banyan_row' }, 'climbing', 'east'));
    run(all, 0.4);
    expect(all.all.get('odalys')!.drawn).toMatchObject({ pose: 'climbing', on: 'stairs', facing: 'east' });
  });

  it('climbs the park ladder from the back', () => {
    const all = residents({ ...odalys, position: { x: 45, y: 15, map: 'lychee_lane' } });
    all.move(moved({ x: 45, y: 14, map: 'lychee_lane' }, 'climbing', 'north'));
    run(all, 0.4);
    expect(all.all.get('odalys')!.drawn).toMatchObject({ pose: 'climbing', on: 'ladder', facing: 'north' });
  });

  it('snaps through a door onto the other map', () => {
    const all = residents({ ...odalys, position: { x: 43, y: 15, map: 'high_street' } });
    all.move(moved({ x: 18, y: 2, map: 'coffee_shop_floor_0' }, 'walking', 'west'));
    all.update(0.01);
    const odalysAt = all.all.get('odalys')!;
    expect(odalysAt.map).toBe('coffee_shop_floor_0');
    expect(odalysAt.at).toEqual({ x: 43, y: 15 });
  });
});

describe('crossing between floors', () => {
  const atFoot: Entity = { ...odalys, position: { x: 14, y: 2, map: 'coffee_shop_floor_0' } };

  it('walks to the foot of the stairs, then climbs them to the other floor', () => {
    const all = residents(atFoot);
    const odalysAt = all.all.get('odalys')!;
    all.move(moved({ x: 15, y: 2, map: 'coffee_shop_floor_0' }, 'climbing', 'east'));
    all.update(0.1);
    expect(odalysAt.under).toBeUndefined();
    run(all, 1 / WALKING_SPEED);
    expect(odalysAt.under).toBeDefined();
    const total = 5;
    run(all, total / CLIMB_SPEED.stairs / 2);
    expect(odalysAt.drawn).toMatchObject({ pose: 'climbing', on: 'stairs', facing: 'east' });
    expect(odalysAt.at.x).toBeCloseTo(41.5, 0);
    expect(odalysAt.at.y).toBeCloseTo(13, 0);
    expect(odalysAt.drawnMap).toBe('coffee_shop_floor_0');
    all.move(moved({ x: 18, y: 2, map: 'coffee_shop_floor_1' }, 'walking', 'east'));
    run(all, 0.2);
    expect(odalysAt.map).toBe('coffee_shop_floor_0');
    run(all, total / CLIMB_SPEED.stairs);
    expect(odalysAt.map).toBe('coffee_shop_floor_1');
    expect(odalysAt.under).toBeUndefined();
    expect(odalysAt.at).toEqual({ x: 43, y: 11 });
  });

  it('holds at the top until the server moves it on', () => {
    const all = residents({ ...odalys, position: { x: 15, y: 2, map: 'coffee_shop_floor_0' } });
    all.move(moved({ x: 15, y: 2, map: 'coffee_shop_floor_0' }, 'climbing', 'east'));
    run(all, 10);
    const odalysAt = all.all.get('odalys')!;
    expect(odalysAt.map).toBe('coffee_shop_floor_0');
    expect(odalysAt.at).toEqual({ x: 43, y: 11 });
  });

  it('starts the climb at once if the arrival comes first', () => {
    const all = residents(atFoot);
    all.move(moved({ x: 15, y: 2, map: 'coffee_shop_floor_0' }, 'climbing', 'east'));
    all.move(moved({ x: 18, y: 2, map: 'coffee_shop_floor_1' }, 'walking', 'east'));
    const odalysAt = all.all.get('odalys')!;
    expect(odalysAt.under?.arrival?.map).toBe('coffee_shop_floor_1');
    run(all, 6);
    expect(odalysAt.map).toBe('coffee_shop_floor_1');
  });

  it('rides the lift facing out, its whole way', () => {
    const all = residents({ ...odalys, position: { x: 16, y: 2, map: 'gallery_floor_0' } });
    const odalysAt = all.all.get('odalys')!;
    all.move(moved({ x: 16, y: 2, map: 'gallery_floor_0' }, 'riding', 'south'));
    all.move(moved({ x: 16, y: 2, map: 'gallery_floor_1' }, 'standing', 'west'));
    run(all, 2 / RIDE_SPEED);
    expect(odalysAt.drawn).toMatchObject({ pose: 'riding', facing: 'south' });
    expect(odalysAt.at.x).toBeCloseTo(41.5);
    expect(odalysAt.at.y).toBeLessThan(15);
    run(all, 5);
    expect(odalysAt.map).toBe('gallery_floor_1');
    expect(odalysAt.drawn).toMatchObject({ pose: 'standing', facing: 'west' });
  });

  it('only rides a lift when riding, and only climbs stairs when climbing', () => {
    const all = residents({ ...odalys, position: { x: 16, y: 2, map: 'gallery_floor_0' } });
    all.move(moved({ x: 16, y: 2, map: 'gallery_floor_0' }, 'climbing', 'south'));
    run(all, 1);
    expect(all.all.get('odalys')!.under).toBeUndefined();
  });
});

describe('going to bed', () => {
  const bedroom = (x: number, pose: Pose = 'standing'): Entity => ({
    ...odalys,
    position: { x, y: 2, map: 'house_3_floor_1' },
    pose,
    facing: 'east',
  });
  const at = (x: number) => ({ x, y: 2, map: 'house_3_floor_1' });

  it('lies down once it reaches its bed, over LIE_SECONDS', () => {
    const all = residents(bedroom(4));
    const odalysAt = all.all.get('odalys')!;
    all.move(moved(at(3), 'sleeping', 'east'));
    all.update(0.1);
    expect(odalysAt.drawn.bed).toBe(0);
    run(all, 1 / WALKING_SPEED);
    expect(odalysAt.drawn.bed).toBeGreaterThan(0);
    expect(odalysAt.drawn.bed).toBeLessThan(1);
    run(all, LIE_SECONDS);
    expect(odalysAt.drawn).toMatchObject({ pose: 'sleeping', bed: 1 });
  });

  it('gets up before it walks off, then catches up', () => {
    const all = residents(bedroom(3, 'sleeping'));
    const odalysAt = all.all.get('odalys')!;
    all.move(moved(at(4), 'walking', 'east'));
    run(all, LIE_SECONDS / 2);
    expect(odalysAt.walker.position.x).toBe(3);
    expect(odalysAt.drawn.bed).toBeCloseTo(0.5, 1);
    all.move(moved(at(5), 'walking', 'east'));
    run(all, LIE_SECONDS / 2 + 0.02);
    expect(odalysAt.drawn.bed).toBe(0);
    expect(odalysAt.walker.position.x).toBeLessThan(3.1);
    run(all, 2 / WALKING_SPEED);
    expect(odalysAt.walker.position.x).toBe(5);
  });

  it('gets up before walking to a bed somewhere else, then lies down there', () => {
    const all = residents(bedroom(3, 'sleeping'));
    const odalysAt = all.all.get('odalys')!;
    all.move(moved(at(4), 'sleeping', 'east'));
    run(all, LIE_SECONDS / 2);
    expect(odalysAt.walker.position.x).toBe(3);
    expect(odalysAt.drawn.bed).toBeCloseTo(0.5, 1);
    run(all, LIE_SECONDS / 2 + 0.02);
    expect(odalysAt.drawn.bed).toBe(0);
    run(all, 1 / WALKING_SPEED + LIE_SECONDS + 0.1);
    expect(odalysAt.walker.position.x).toBe(4);
    expect(odalysAt.drawn.bed).toBe(1);
  });

  it('is shown lying at once from a snapshot, and up at once from the next', () => {
    const all = residents(bedroom(3, 'sleeping'));
    const odalysAt = all.all.get('odalys')!;
    all.update(0.01);
    expect(odalysAt.drawn.bed).toBe(1);
    all.reset([bedroom(5)]);
    all.update(0.01);
    expect(odalysAt.drawn.bed).toBe(0);
    all.reset([bedroom(3, 'sleeping')]);
    all.update(0.01);
    expect(odalysAt.drawn.bed).toBe(1);
    expect(odalysAt.walker.position.x).toBe(3);
  });
});

describe('the player', () => {
  it('starts where the snapshot says, or at home once they collapse', () => {
    const player = { id: 'player', kind: 'player', name: 'You', position: { x: 51, y: 15, map: 'high_street' } };
    server.dispatch(JSON.stringify({ type: 'snapshot', time: '2026-03-14T09:10:03Z', map_id: 'high_street', entities: [player], conversations: [] }));
    expect(sideResidents.start).toEqual({ x: 51, y: 15, map: 'high_street' });

    server.dispatch(JSON.stringify({ type: 'player_collapsed', position: { x: 13, y: 2, map: 'maker_space_floor_0' } }));

    expect(sideResidents.start).toEqual({ x: 13, y: 2, map: 'maker_space_floor_0' });
  });
});
