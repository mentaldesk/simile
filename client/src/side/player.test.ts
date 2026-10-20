import { describe, expect, it } from 'vitest';
import { PLAYER_SPEED } from '../world/tuning';
import { village } from './content';
import { RIDE_SPEED } from './motion';
import { PLAYER_CLIMB, SidePlayer, type Controls, type MapPosition } from './player';

const idle: Controls = { x: 0, y: 0, use: false };
const press = (controls: Partial<Controls>): Controls => ({ ...idle, ...controls });

function hold(player: SidePlayer, controls: Controls, seconds: number) {
  let door;
  for (let t = 0; t < seconds; t += 1 / 60) door ??= player.update(controls, 1 / 60);
  return door;
}

const at = (position: MapPosition) => new SidePlayer(village, position);

describe('walking', () => {
  it('walks left and right along the street at its speed, facing the way it goes', () => {
    const player = at({ x: 10, y: 15, map: 'high_street' });
    hold(player, press({ x: 1 }), 1);
    expect(player.position.x).toBeCloseTo(10 + PLAYER_SPEED, 1);
    expect(player.drawn).toMatchObject({ pose: 'walking', facing: 'east' });
    hold(player, press({ x: -1 }), 0.1);
    expect(player.facing).toBe('west');
    player.update(idle, 1 / 60);
    expect(player.drawn.pose).toBe('standing');
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

describe('doors', () => {
  it('goes through a door on E or up in front of it, not walking past', () => {
    const player = at({ x: 41, y: 15, map: 'high_street' });
    expect(hold(player, press({ x: 1 }), 1)).toBeUndefined();
    const front = at({ x: 43, y: 15, map: 'high_street' });
    expect(front.update(press({ y: -1 }), 1 / 60)?.id).toBe('coffee_shop');
    expect(at({ x: 43, y: 15, map: 'high_street' }).update(press({ use: true }), 1 / 60)?.to.map).toBe(
      'coffee_shop_floor_0',
    );
  });

  it("doesn't go straight back while up is still held after arriving", () => {
    const player = at({ x: 43, y: 15, map: 'high_street' });
    player.place({ x: 18, y: 2, map: 'coffee_shop_floor_0' });
    expect(hold(player, press({ y: -1 }), 0.5)).toBeUndefined();
    player.update(idle, 1 / 60);
    expect(player.update(press({ y: -1 }), 1 / 60)?.to.map).toBe('high_street');
  });

  it('leaves a building by its front door on down', () => {
    const player = at({ x: 18, y: 2, map: 'coffee_shop_floor_0' });
    player.update(idle, 1 / 60);
    expect(player.update(press({ y: 1 }), 1 / 60)?.to).toEqual({ map: 'high_street', x: 43, y: 15 });
  });
});

describe('stairs and ladders between floors', () => {
  it('starts on E at the foot, then climbs while up is held, stopping anywhere', () => {
    const player = at({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
    hold(player, press({ y: -1 }), 0.5);
    expect(player.climbing).toBeUndefined();
    player.update(press({ use: true }), 1 / 60);
    expect(player.climbing).toBe('stairs');
    hold(player, press({ y: -1 }), 1);
    const partway = { ...player.at };
    expect(partway.x).toBeLessThan(40);
    expect(partway.y).toBeLessThan(15);
    expect(player.drawn).toMatchObject({ pose: 'climbing', on: 'stairs', facing: 'west' });
    expect(player.mapPosition).toEqual({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
    hold(player, idle, 1);
    expect(player.at).toEqual(partway);
    hold(player, press({ y: -1 }), (4 * Math.SQRT2) / PLAYER_CLIMB.stairs);
    expect(player.climbing).toBeUndefined();
    expect(player.mapPosition).toEqual({ x: 11, y: 2, map: 'coffee_shop_floor_1' });
  });

  it('climbs with left and right along the flight too, and steps back off at the foot', () => {
    const player = at({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
    player.update(press({ use: true }), 1 / 60);
    hold(player, press({ x: -1 }), 0.5);
    expect(player.at.y).toBeLessThan(15);
    hold(player, press({ x: 1 }), 2);
    expect(player.climbing).toBeUndefined();
    expect(player.mapPosition).toMatchObject({ y: 2, map: 'coffee_shop_floor_0' });
    expect(player.position.x).toBeGreaterThan(15);
  });

  it('climbs down from the top on down', () => {
    const player = at({ x: 11, y: 2, map: 'coffee_shop_floor_1' });
    player.update(press({ use: true }), 1 / 60);
    hold(player, press({ y: 1 }), 4);
    expect(player.mapPosition).toEqual({ x: 15, y: 2, map: 'coffee_shop_floor_0' });
  });

  it('climbs a ladder from the back', () => {
    const player = at({ x: 6, y: 2, map: 'maker_space_floor_1' });
    player.update(press({ use: true }), 1 / 60);
    hold(player, press({ y: -1 }), 1);
    expect(player.drawn).toMatchObject({ pose: 'climbing', on: 'ladder', facing: 'north' });
    expect(player.at.x).toBe(8);
    hold(player, press({ y: -1 }), 3);
    expect(player.map).toBe('maker_space_floor_2');
  });

  it('rides a lift all the way on E', () => {
    const player = at({ x: 16, y: 2, map: 'gallery_floor_0' });
    player.update(press({ use: true }), 1 / 60);
    hold(player, idle, 1 / RIDE_SPEED);
    expect(player.drawn).toMatchObject({ pose: 'riding', facing: 'south' });
    hold(player, idle, 4 / RIDE_SPEED);
    expect(player.mapPosition).toEqual({ x: 16, y: 2, map: 'gallery_floor_1' });
  });
});

describe('stairs and ladders on a street', () => {
  it("takes Banyan Row's stairs down to the river with E, then along with right", () => {
    const player = at({ x: 53, y: 15, map: 'banyan_row' });
    player.update(press({ use: true }), 1 / 60);
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

  it('climbs the park ladder and steps off onto the lookout', () => {
    const player = at({ x: 45, y: 15, map: 'lychee_lane' });
    player.update(press({ use: true }), 1 / 60);
    hold(player, press({ y: -1 }), 1);
    expect(player.position.x).toBe(45);
    expect(player.position.y).toBeLessThan(15);
    hold(player, press({ y: -1 }), 4);
    expect(player.position).toEqual({ x: 46, y: 12 });
    hold(player, press({ x: 1 }), 1);
    expect(player.position.x).toBe(48);
  });

  it('gets back on the ladder from the lookout with E', () => {
    const player = at({ x: 46, y: 12, map: 'lychee_lane' });
    player.update(press({ use: true }), 1 / 60);
    hold(player, press({ y: 1 }), 6);
    expect(player.position).toEqual({ x: 45, y: 15 });
  });
});
