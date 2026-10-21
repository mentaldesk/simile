import { describe, expect, it } from 'vitest';
import type { Facing } from '../net/protocol';
import fixtures from './flat.fixture.json';
import { SIDE_PIECES, STRAIGHT_PIECES, type FlatDoll, type PieceName } from './manifest';
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
/** The flat-doll route's dolls for a few residents' looks: average, broad, slim, and an apron. */
const dolls = fixtures as unknown as Record<string, FlatDoll>;
const doll = dolls.desmond;

/** Where `joint` of the piece `part` places ends up, by Phaser's clockwise turn. */
function jointOf(doll: FlatDoll, part: Placement, joint: string): { x: number; y: number } {
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
        expectJoined(posed(doll, pose, facing, phase));
      }
    }
  });

  function expectJoined(p: Posed): void {
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

  describe('running', () => {
    const run = (phase: number, facing: Facing = 'east', w = 1) => posed(doll, 'walking', facing, phase, { run: w });
    const views: Facing[] = ['east', 'south', 'north'];
    /** Where the legs are furthest apart, and where one is under the hips. */
    const AIRBORNE = [0.25, 0.75];
    const LANDED = [0, 0.5];

    it.each(Object.keys(dolls))('draws every piece, joined, in every view for %s', (id) => {
      for (const facing of FACINGS) {
        for (const phase of PHASES) {
          for (const w of [0.3, 1]) {
            const p = posed(dolls[id], 'walking', facing, phase, { run: w });
            expect(p.parts).toHaveLength(12);
            for (const part of p.parts) expect(Number.isFinite(part.x + part.y + part.angle + part.scaleY)).toBe(true);
          }
        }
      }
      for (const facing of views) for (const phase of PHASES) expectJoined(run(phase, facing));
    });

    it('leaves the walk as it was when not running', () => {
      for (const facing of FACINGS) {
        for (const phase of PHASES) {
          expect(posed(doll, 'walking', facing, phase, { run: 0 })).toEqual(posed(doll, 'walking', facing, phase));
        }
      }
    });

    it('has both feet off the ground while the legs are furthest apart, in every view', () => {
      for (const facing of views) {
        for (const phase of AIRBORNE) {
          expect(lowest(doll, run(phase, facing).parts), `${facing} at ${phase}`).toBeLessThan(-doll.unit * 4);
        }
        for (const phase of LANDED) {
          expect(lowest(doll, run(phase, facing).parts), `${facing} at ${phase}`).toBeCloseTo(0, 6);
        }
      }
      const shoes = find(run(0.25), 'shoe');
      expect(shoes.every((shoe) => shoe.y < -doll.unit * 4)).toBe(true);
    });

    it('bounces, the hips highest in the air and lower than walking on the ground', () => {
      const hips = (p: Posed) => p.parts.find((x) => x.piece.startsWith('torso'))!.y;
      for (const facing of views) {
        expect(hips(run(0.25, facing))).toBeLessThan(hips(run(0, facing)) - doll.unit * 2);
        expect(hips(run(0, facing))).toBeGreaterThan(hips(posed(doll, 'walking', facing, 0)));
      }
    });

    it('leans in, further than walking', () => {
      for (const phase of PHASES) {
        expect(find(run(phase), 'torso')[0].angle).toBeGreaterThan(find(posed(doll, 'walking', 'east', phase), 'torso')[0].angle + 8);
      }
    });

    it('bends the elbows and pumps the arms', () => {
      for (const phase of PHASES) {
        const p = run(phase);
        const [far, near] = [find(p, 'upper_arm'), find(p, 'lower_arm')].map((arms) => arms.map((arm) => arm.angle));
        far.forEach((upper, i) => expect(Math.abs(near[i] - upper)).toBeGreaterThanOrEqual(70));
      }
      const swing = (phase: number) => find(run(phase), 'upper_arm')[1].angle;
      expect(Math.abs(swing(0.25) - swing(0.75))).toBeGreaterThan(60);
      const front = (phase: number) => find(run(phase, 'south'), 'lower_arm').map((arm) => arm.scaleY);
      expect(Math.max(...front(0.25), ...front(0.75))).toBeLessThan(0.85);
    });

    it('lifts the knees higher and takes a longer stride than walking', () => {
      const knees = (w: number) =>
        Math.min(...PHASES.flatMap((phase) => find(run(phase, 'east', w), 'lower_leg').map((p) => p.y)));
      const stride = (w: number) =>
        Math.max(...PHASES.map((phase) => Math.abs(find(run(phase, 'east', w), 'shoe').reduce((a, b) => a - b.x, 0))));
      expect(knees(1)).toBeLessThan(knees(0) - doll.unit * 4);
      expect(stride(1)).toBeGreaterThan(stride(0));
    });

    it('blends from a walk to a run, turning each piece part of the way', () => {
      for (const phase of PHASES) {
        const [walking, running] = [run(phase, 'east', 0), run(phase, 'east', 1)];
        for (const w of [0.01, 0.5, 0.99]) {
          run(phase, 'east', w).parts.forEach((part, i) => {
            const [from, to] = [walking.parts[i].angle, running.parts[i].angle];
            expect(part.angle).toBeCloseTo(from + (to - from) * w, 6);
          });
        }
        expect(run(phase, 'east', 1e-9).parts[0].angle).toBeCloseTo(walking.parts[0].angle, 6);
        expect(run(phase, 'south', 0.5).parts).toHaveLength(12);
      }
    });
  });

  it('stands about its height tall, hair and all', () => {
    for (const doll of Object.values(dolls)) {
      const height = standingHeight(doll) / doll.unit;
      expect(height).toBeGreaterThan(doll.height * 0.98);
      expect(height).toBeLessThan(doll.height * 1.12);
    }
  });
});
