import { describe, expect, it } from 'vitest';
import type { Facing } from '../net/protocol';
import { dolls } from './assets';
import { SIDE_PIECES, STRAIGHT_PIECES, type DollManifest, type PieceName } from './manifest';
import {
  FAR,
  lowest,
  posed,
  standingHeight,
  viewOf,
  type DollPose,
  type Placement,
  type Posed,
} from './rig';

const POSES: DollPose[] = [
  'standing',
  'walking',
  'sitting',
  'reading',
  'working',
  'looking',
  'climbing',
  'riding',
  'jumping',
];
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
const PLANTED: DollPose[] = [
  'standing',
  'walking',
  'sitting',
  'reading',
  'working',
  'looking',
  'riding',
];
const PHASES = [0, 0.2, 0.45, 0.7, 0.95];
const doll = dolls.desmond;

/** Where `joint` of the piece `part` places ends up, by Phaser's clockwise turn. */
function jointOf(doll: DollManifest, part: Placement, joint: string): { x: number; y: number } {
  const spec = doll.pieces[part.piece];
  const [jx, jy] = spec.joints[joint];
  const v = { x: jx - spec.pivot[0], y: (jy - spec.pivot[1]) * part.scaleY };
  const a = (part.angle * Math.PI) / 180;
  return {
    x: part.x + v.x * Math.cos(a) - v.y * Math.sin(a),
    y: part.y + v.x * Math.sin(a) + v.y * Math.cos(a),
  };
}

const find = (posed: Posed, piece: PieceName) => posed.parts.filter((p) => p.piece === piece);

describe('the committed dolls', () => {
  it('has every resident and the player, flat and painted', () => {
    expect(Object.keys(dolls).sort()).toEqual([
      'desmond',
      'henrietta',
      'ingrid',
      'kofi',
      'lachlan',
      'marguerite',
      'mirela',
      'odalys',
      'player',
      'priya',
      'raymond',
      'tobias',
    ]);
    for (const doll of Object.values(dolls)) {
      expect(doll.flat).toMatch(/-flat\.webp$/);
      expect(doll.painted).toMatch(/-painted\.webp$/);
    }
  });
});

describe('posed', () => {
  it.each(Object.keys(dolls))('draws every pose in every facing for %s', (id) => {
    const doll = dolls[id];
    for (const pose of POSES) {
      for (const facing of FACINGS) {
        for (const phase of PHASES) {
          const { view, parts } = posed(doll, pose, facing, phase);
          const pieces = new Set(parts.map((p) => p.piece));
          const wanted: readonly PieceName[] =
            view === 'side'
              ? SIDE_PIECES
              : STRAIGHT_PIECES.filter((p) => p.includes(view) || p === 'shoe_front');
          expect([...pieces].sort()).toEqual(
            [
              ...wanted,
              ...(view === 'side'
                ? []
                : (['upper_arm', 'lower_arm', 'upper_leg', 'lower_leg'] as const)),
            ].sort(),
          );
          expect(parts).toHaveLength(12);
          for (const part of parts) {
            for (const value of [part.x, part.y, part.angle, part.scaleY, part.shade]) {
              expect(Number.isFinite(value)).toBe(true);
            }
          }
          if (PLANTED.includes(pose)) expect(lowest(doll, parts)).toBeCloseTo(0, 6);
        }
      }
    }
  });

  it('faces right for eastward, left for westward, back for north and front for south', () => {
    expect(viewOf('east')).toEqual({ view: 'side', flip: false });
    expect(viewOf('north_east')).toEqual({ view: 'side', flip: false });
    expect(viewOf('south_west')).toEqual({ view: 'side', flip: true });
    expect(viewOf('west')).toEqual({ view: 'side', flip: true });
    expect(viewOf('north')).toEqual({ view: 'back', flip: false });
    expect(viewOf('south')).toEqual({ view: 'front', flip: false });
    expect(find(posed(doll, 'standing', 'north'), 'head_back')).toHaveLength(1);
    expect(find(posed(doll, 'standing', 'south'), 'head_front')).toHaveLength(1);
  });

  it.each(POSES)('joins every %s piece at its parent joint, in every view', (pose) => {
    for (const facing of ['east', 'south', 'north'] as Facing[]) {
      for (const phase of PHASES) {
        const p = posed(doll, pose, facing, phase);
        const torso = p.parts.find((x) => x.piece.startsWith('torso'))!;
        const head = p.parts.find((x) => x.piece.startsWith('head'))!;
        const neck = jointOf(doll, torso, 'neck');
        expect(head.x).toBeCloseTo(neck.x, 6);
        const thighs = find(p, 'upper_leg');
        const shins = find(p, 'lower_leg');
        const uppers = find(p, 'upper_arm');
        const forearms = find(p, 'lower_arm');
        const shoes = p.parts.filter((x) => x.piece.startsWith('shoe'));
        thighs.forEach((thigh, i) => {
          const knee = jointOf(doll, thigh, 'knee');
          expect(shins[i].x).toBeCloseTo(knee.x, 6);
          expect(shins[i].y).toBeCloseTo(knee.y, 6);
          const ankle = jointOf(doll, shins[i], 'ankle');
          expect(shoes[i].x).toBeCloseTo(ankle.x, 6);
          expect(shoes[i].y).toBeCloseTo(ankle.y, 6);
        });
        uppers.forEach((upper, i) => {
          const elbow = jointOf(doll, upper, 'elbow');
          expect(forearms[i].x).toBeCloseTo(elbow.x, 6);
          expect(forearms[i].y).toBeCloseTo(elbow.y, 6);
        });
      }
    }
  });

  it('draws the far arm and leg first, and darker', () => {
    const { parts } = posed(doll, 'walking', 'east', 0.3);

    expect(parts.slice(0, 5).map((p) => [p.piece, p.shade])).toEqual([
      ['upper_arm', FAR],
      ['lower_arm', FAR],
      ['upper_leg', FAR],
      ['lower_leg', FAR],
      ['shoe', FAR],
    ]);
    expect(parts.slice(-2).map((p) => p.piece)).toEqual(['upper_arm', 'lower_arm']);
    expect(parts.slice(5).every((p) => p.shade === 1)).toBe(true);
  });

  it('walks in a cycle, the feet passing each other', () => {
    const shoes = (phase: number) =>
      find(posed(doll, 'walking', 'east', phase), 'shoe').map((s) => s.x);

    expect(posed(doll, 'walking', 'east', 1)).toEqual(posed(doll, 'walking', 'east', 0));
    const [farQuarter, nearQuarter] = shoes(0.25);
    const [farLate, nearLate] = shoes(0.75);
    expect(nearQuarter).toBeGreaterThan(farQuarter);
    expect(nearLate).toBeLessThan(farLate);
  });

  it('climbs a ladder from the back with the hands above the head', () => {
    const climb = posed(doll, 'climbing', 'north', 0.25);
    const head = find(climb, 'head_back')[0];
    const hands = find(climb, 'lower_arm').map((arm) => jointOf(doll, arm, 'hand'));

    expect(hands.every((hand) => hand.y < head.y)).toBe(true);
    expect(climb.parts.slice(-4).map((p) => p.piece)).toEqual([
      'upper_arm',
      'upper_arm',
      'lower_arm',
      'lower_arm',
    ]);
    const stand = posed(doll, 'standing', 'north');
    expect(find(climb, 'torso_back')[0].y).toBeCloseTo(find(stand, 'torso_back')[0].y, 6);
  });

  it('climbs stairs from the side as a walk with the knees lifted', () => {
    const knees = (pose: DollPose, on?: 'ladder' | 'stairs') =>
      Math.min(
        ...[0.1, 0.35, 0.6, 0.85].flatMap((phase) =>
          find(posed(doll, pose, 'east', phase, { on }), 'lower_leg').map((p) => p.y),
        ),
      );

    expect(knees('climbing')).toBeLessThan(knees('walking') - doll.unit * 2);
    expect(knees('climbing', 'stairs')).toBe(knees('climbing'));
    const ladder = posed(doll, 'climbing', 'east', 0.25, { on: 'ladder' });
    expect(
      find(ladder, 'lower_arm').some(
        (arm) => jointOf(doll, arm, 'hand').y < find(ladder, 'head')[0].y,
      ),
    ).toBe(true);
  });

  it('sits with the hips down near the feet', () => {
    for (const facing of ['east', 'south', 'north'] as Facing[]) {
      const hips = (p: Posed) => p.parts.find((x) => x.piece.startsWith('torso'))!.y;
      expect(hips(posed(doll, 'sitting', facing))).toBeGreaterThan(
        hips(posed(doll, 'standing', facing)) + doll.unit * 10,
      );
      expect(hips(posed(doll, 'reading', facing, 0, { seated: true }))).toBe(
        hips(posed(doll, 'sitting', facing)),
      );
    }
  });

  it('looks up and reads looking down', () => {
    const head = (pose: DollPose) => find(posed(doll, pose, 'east'), 'head')[0].angle;

    expect(head('looking')).toBeLessThan(head('standing') - 8);
    expect(head('reading')).toBeGreaterThan(head('standing') + 8);
  });

  it('works with the hands moving', () => {
    const hand = (phase: number) =>
      find(posed(doll, 'working', 'east', phase), 'lower_arm')[1].angle;

    expect(Math.abs(hand(0.25) - hand(0.75))).toBeGreaterThan(30);
  });

  it('jumps off the ground and rides standing', () => {
    expect(lowest(doll, posed(doll, 'jumping', 'east').parts)).toBeLessThan(-doll.unit * 5);
    expect(lowest(doll, posed(doll, 'jumping', 'south').parts)).toBeLessThan(-doll.unit * 5);
    expect(lowest(doll, posed(doll, 'riding', 'south').parts)).toBeCloseTo(0, 6);
  });

  it('stands about its height tall, hair and all', () => {
    for (const doll of Object.values(dolls)) {
      const height = standingHeight(doll) / doll.unit;
      expect(height).toBeGreaterThan(doll.height * 0.98);
      expect(height).toBeLessThan(doll.height * 1.12);
    }
  });
});
