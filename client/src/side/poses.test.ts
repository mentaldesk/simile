import { describe, expect, it } from 'vitest';
import { dolls } from '../dolls/assets';
import { placed, shown } from '../dolls/sprite';
import { village } from './content';
import { DOLL_M, feetOf, FURNITURE_DROP_M, furniturePlacement, PPM } from './layout';
import type { Placed } from './maps';
import { facesLeft, hiddenInFront, PoseCache, SEAT_M, seatHeight, STEPS } from './poses';

describe('the pose cache', () => {
  const figure = dolls.kofi;

  it("keeps each step of a cycle's frame, worked out once", () => {
    const cache = new PoseCache(figure);
    const first = cache.get('walking', 'east', 0.26);
    expect(cache.get('walking', 'east', 0.26 + 0.1 / STEPS)).toBe(first);
    expect(cache.get('walking', 'east', 1.26)).toBe(first);
    expect(first).toEqual(shown(figure, 'walking', 'east', Math.floor(0.26 * STEPS) / STEPS));
    expect(cache.get('walking', 'east', 0.5)).not.toBe(first);
    expect(cache.size).toBe(2);
  });

  it('mirrors the westward facings and shares the rest', () => {
    const cache = new PoseCache(figure);
    expect(facesLeft('north_west')).toBe(true);
    expect(facesLeft('east')).toBe(false);
    expect(cache.get('walking', 'west', 0.1).flip).toBe(true);
    expect(cache.get('walking', 'east', 0.1).flip).toBe(false);
    expect(cache.get('standing', 'south', 0)).toBe(cache.get('standing', 'east', 0));
    expect(cache.get('standing', 'north', 0)).toBe(cache.get('looking', 'south_east', 0));
  });

  it('sits at a desk, climbs a ladder from behind and takes stairs walking', () => {
    const cache = new PoseCache(figure);
    expect(cache.get('working', 'north', 0, true).frame).toBe(figure.poses.sit[0]);
    expect(cache.get('working', 'north', 0).frame).toBe(figure.poses.stand[0]);
    expect(cache.get('climbing', 'north', 0, false, 'ladder').frame).toBe(figure.poses.climb[0]);
    expect(figure.poses.walk).toContain(cache.get('climbing', 'east', 0.1, false, 'stairs').frame);
  });

  it('runs once a walk is more than half a run', () => {
    const cache = new PoseCache(figure);
    expect(figure.poses.walk).toContain(cache.get('walking', 'east', 0.1, false, undefined, 0.4).frame);
    expect(figure.poses.run).toContain(cache.get('walking', 'east', 0.1, false, undefined, 0.6).frame);
    expect(cache.get('standing', 'east', 0, false, undefined, 1)).toBe(cache.get('standing', 'east', 0));
  });
});

describe('a seat', () => {
  const at = (type: string, x: number, w = 1): Placed => ({ name: type, type, x, y: 2, w, h: 1, props: {} });
  const map = {
    spots: [at('seat', 1), at('seat', 4), at('bar', 5), at('seat', 6), at('desk', 8), at('standing', 9)],
    furniture: [at('cafe_table', 1, 2), at('noodle_counter', 4, 2), at('stool', 4), at('stool', 5), at('bench', 6, 2)],
  };
  const drawn = (type: string) => SEAT_M[type] - FURNITURE_DROP_M;

  it('is the front edge of the seat of the piece under it, as drawn, and nothing off a seat', () => {
    expect(seatHeight(map, 1, 2)).toBeCloseTo(drawn('cafe_table'));
    expect(seatHeight(map, 4, 2)).toBeCloseTo(drawn('stool'));
    expect(seatHeight(map, 5, 2)).toBeCloseTo(drawn('stool'));
    expect(seatHeight(map, 6, 2)).toBeCloseTo(drawn('bench'));
    expect(seatHeight(map, 8, 2)).toBeCloseTo(drawn('cafe_table'));
    expect(seatHeight(map, 9, 2)).toBe(0);
    expect(seatHeight(map, 3, 2)).toBe(0);
  });

  it('is under every seat in the village, and every sitter rests on it', () => {
    const seats = [...village.maps.values()].flatMap((map) =>
      map.spots.filter(({ type }) => type === 'seat' || type === 'bar').map((spot) => ({ map, spot })),
    );
    expect(seats.length).toBe(64);
    for (const { map, spot } of seats) {
      const piece = map.furniture.find(
        (f) => f.type in SEAT_M && f.x <= spot.x && spot.x < f.x + f.w && f.y <= spot.y && spot.y < f.y + f.h,
      );
      expect(piece, `${map.id} ${spot.name}`).toBeDefined();
      const seat = seatHeight(map, spot.x, spot.y);
      const front = furniturePlacement(piece!, map).y - SEAT_M[piece!.type] * PPM;
      for (const figure of Object.values(dolls)) {
        const scale = (DOLL_M * PPM) / figure.height;
        const thighs = placed(figure, shown(figure, 'sitting', 'east', 0, { seat })).y * scale;
        expect(feetOf(map.offset.y + spot.y) + thighs).toBeCloseTo(front, 6);
      }
    }
  });
});

describe('a figure in front of an open dollhouse', () => {
  it('is left out rather than drawn see-through, unless it’s inside or the player', () => {
    expect(hiddenInFront(false, false, 0.35)).toBe(true);
    expect(hiddenInFront(false, false, 0.9)).toBe(true);
    expect(hiddenInFront(false, false, 1)).toBe(false);
    expect(hiddenInFront(true, false, 0.35)).toBe(false);
    expect(hiddenInFront(false, true, 0.35)).toBe(false);
  });
});
