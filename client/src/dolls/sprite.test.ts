import { describe, expect, it } from 'vitest';
import type { Facing } from '../net/protocol';
import { dolls } from './assets';
import type { FigureManifest, PaintedPose, SpritePose } from './manifest';
import type { DollPose, PoseOptions } from './rig';
import { LANDING_SQUASH, leap, placed, shown, spritePose, WALK_BOB } from './sprite';

const frame = (x: number, feet: [number, number]) => ({ frame: [x, 0, 60, 170] as [number, number, number, number], feet });

const figure: FigureManifest = {
  id: 'test',
  ppm: 80,
  height: 163.2,
  painted: 'test.webp',
  frames: {
    stand: frame(0, [30, 166]),
    stride: frame(62, [26, 167]),
    pass: frame(124, [31, 165]),
    run: frame(186, [22, 160]),
    run_pass: frame(248, [28, 166]),
    sit: { ...frame(310, [33, 120]), seat: [33, 90] },
    climb: frame(372, [30, 168]),
  },
  poses: {
    stand: ['stand'],
    walk: ['stride', 'pass', 'stride', 'pass'],
    run: ['run', 'run_pass', 'run', 'run_pass'],
    sit: ['sit'],
    climb: ['climb'],
  },
};

const frames = (pose: DollPose, facing: Facing, options: PoseOptions = {}, steps = 8) =>
  Array.from({ length: steps }, (_, i) => shown(figure, pose, facing, i / steps, options).frame);

describe('a pose', () => {
  it.each<[DollPose, Facing, PoseOptions, SpritePose]>([
    ['standing', 'south', {}, 'stand'],
    ['looking', 'east', {}, 'stand'],
    ['riding', 'south', {}, 'stand'],
    ['walking', 'west', {}, 'walk'],
    ['walking', 'east', { run: 0.4 }, 'walk'],
    ['walking', 'east', { run: 0.6 }, 'run'],
    ['sitting', 'east', {}, 'sit'],
    ['reading', 'east', { seated: true }, 'sit'],
    ['working', 'north', {}, 'stand'],
    ['climbing', 'north', {}, 'climb'],
    ['climbing', 'east', {}, 'walk'],
    ['climbing', 'east', { on: 'ladder' }, 'climb'],
    ['climbing', 'south', { on: 'stairs' }, 'walk'],
  ])('%s facing %s with %o is drawn as %s', (pose, facing, options, kind) => {
    expect(spritePose(pose, facing, options)).toBe(kind);
  });

  it('picks its frames in order through the cycle, any number', () => {
    expect(frames('walking', 'east')).toEqual(['stride', 'stride', 'pass', 'pass', 'stride', 'stride', 'pass', 'pass']);
    expect(frames('walking', 'east', { run: 1 }, 4)).toEqual(['run', 'run_pass', 'run', 'run_pass']);
    expect(shown(figure, 'walking', 'east', 3.3).frame).toBe(shown(figure, 'walking', 'east', 0.3).frame);
    expect(shown(figure, 'walking', 'east', -0.7).frame).toBe(shown(figure, 'walking', 'east', 0.3).frame);
    expect(new Set(frames('sitting', 'west'))).toEqual(new Set(['sit']));
    expect(new Set(frames('standing', 'north'))).toEqual(new Set(['stand']));
  });

  it('mirrors west and keeps north and south the three-quarter figure', () => {
    for (const facing of ['west', 'south_west', 'north_west'] as Facing[]) {
      expect(shown(figure, 'walking', facing, 0.1).flip).toBe(true);
    }
    for (const facing of ['east', 'south', 'north', 'north_east'] as Facing[]) {
      expect(shown(figure, 'standing', facing).flip).toBe(false);
    }
  });

  it('climbs a ladder from behind, turning from side to side', () => {
    expect(shown(figure, 'climbing', 'north', 0.2).flip).toBe(false);
    expect(shown(figure, 'climbing', 'north', 0.7).flip).toBe(true);
  });

  it('bobs and sways a little as it walks, and only then', () => {
    const steps = Array.from({ length: 48 }, (_, i) => shown(figure, 'walking', 'east', i / 48));
    expect(Math.max(...steps.map((s) => s.bob))).toBeCloseTo(WALK_BOB, 3);
    expect(Math.min(...steps.map((s) => s.bob))).toBeCloseTo(0, 3);
    expect(Math.max(...steps.map((s) => Math.abs(s.sway)))).toBeLessThanOrEqual(2);
    const passing = steps.filter((s) => s.frame === 'pass').map((s) => s.bob);
    const striding = steps.filter((s) => s.frame === 'stride').map((s) => s.bob);
    expect(Math.max(...passing)).toBeGreaterThan(Math.max(...striding));
    expect(shown(figure, 'sitting', 'east', 0.3)).toMatchObject({ bob: 0, sway: 0 });
  });
});

describe('where a frame is drawn', () => {
  it('keeps the feet on the origin in every frame, facing either way', () => {
    for (const [name, { frame: box, feet }] of Object.entries(figure.frames)) {
      const [, , w, h] = box;
      for (const flip of [false, true]) {
        const { originX, originY } = placed(figure, { pose: 'stand', frame: name, flip, bob: 0, sway: 0, seat: 0 });
        const drawnFeet = flip ? w - feet[0] : feet[0];
        expect(originX * w).toBeCloseTo(drawnFeet);
        expect(originY * h).toBeCloseTo(feet[1]);
      }
    }
  });

  it('turns the other way when mirrored', () => {
    const east = placed(figure, { pose: 'walk', frame: 'stride', flip: false, bob: 0.01, sway: 1.5, seat: 0 });
    const west = placed(figure, { pose: 'walk', frame: 'stride', flip: true, bob: 0.01, sway: 1.5, seat: 0 });
    expect(west.angle).toBe(-east.angle);
    expect(east.y).toBeCloseTo(-0.01 * figure.height);
  });
});

describe('sitting', () => {
  it('faces the way its seat does, mirrored for a west-facing one', () => {
    expect(shown(figure, 'sitting', 'west', 0, { seat: 0.45 })).toMatchObject({ frame: 'sit', flip: true, seat: 0.45 });
    expect(shown(figure, 'working', 'west', 0, { seated: true, seat: 0.7 })).toMatchObject({ frame: 'sit', flip: true });
    expect(shown(figure, 'sitting', 'east', 0, { seat: 0.45 }).flip).toBe(false);
  });

  it('sits on the seat, where it sits over the seat and that high', () => {
    const [, , w, h] = figure.frames.sit.frame;
    for (const flip of [false, true]) {
      const at = placed(figure, { pose: 'sit', frame: 'sit', flip, bob: 0, sway: 0, seat: 0.45 });
      expect(at.originX * w).toBeCloseTo(flip ? w - 33 : 33);
      expect(at.originY * h).toBeCloseTo(90);
      expect(at.y).toBeCloseTo(-0.45 * figure.ppm);
    }
    const floor = placed(figure, { pose: 'sit', frame: 'sit', flip: false, bob: 0, sway: 0, seat: 0 });
    expect(floor.originY * h).toBeCloseTo(120);
  });
});

describe('the committed figures', () => {
  it('stand each frame on its feet, at the bottom of the frame or under it in the air, under the head', () => {
    for (const doll of Object.values(dolls)) {
      for (const [name, { frame: box, feet }] of Object.entries(doll.frames)) {
        const [, , w, h] = box;
        expect(feet[1], `${doll.id} ${name}`).toBeGreaterThan(h - 8);
        expect(feet[1], `${doll.id} ${name}`).toBeLessThanOrEqual(h + 0.3 * doll.height);
        expect(feet[0], `${doll.id} ${name}`).toBeGreaterThan(w * 0.15);
        expect(feet[0], `${doll.id} ${name}`).toBeLessThan(w * 0.85);
      }
    }
  });

  it('sit on their thighs, with their feet hanging below the seat', () => {
    for (const doll of Object.values(dolls)) {
      const { frame: box, seat } = doll.frames.sit;
      expect(seat, doll.id).toBeDefined();
      const below = box[3] - seat![1];
      expect(below / doll.height, doll.id).toBeGreaterThan(0.1);
      expect(below / doll.height, doll.id).toBeLessThan(0.35);
    }
  });

  it('draw every frame at the standing figure’s scale', () => {
    for (const doll of Object.values(dolls)) {
      for (const [name, { frame: box }] of Object.entries(doll.frames)) {
        if (name === 'lie') continue;
        expect(box[3], `${doll.id} ${name}`).toBeLessThan(doll.height * 1.2);
        expect(box[3], `${doll.id} ${name}`).toBeGreaterThan(doll.height * 0.75);
      }
    }
  });

  it('play every pose from frames they have', () => {
    for (const doll of Object.values(dolls)) {
      for (const pose of ['stand', 'walk', 'run', 'sit', 'climb'] as PaintedPose[]) {
        expect(doll.poses[pose].length, `${doll.id} ${pose}`).toBeGreaterThan(0);
        for (const name of doll.poses[pose]) expect(doll.frames[name], `${doll.id} ${name}`).toBeDefined();
      }
    }
  });
});

describe('a jump and a landing', () => {
  const leaping: FigureManifest = { ...figure, frames: { ...figure.frames, run_pass: frame(248, [28, 196]) } };
  const bottom = (doll: FigureManifest, name: string) => {
    const { originY, y } = placed(doll, shown(doll, 'jumping', 'east'));
    return y + (1 - originY) * doll.frames[name].frame[3];
  };

  it('leaps in the run frame furthest off the ground, its lowest point on the ground line', () => {
    expect(spritePose('jumping', 'east')).toBe('jump');
    expect(leap(leaping)).toBe('run_pass');
    expect(shown(leaping, 'jumping', 'west', 0.7)).toMatchObject({ pose: 'jump', frame: 'run_pass', flip: true });
    expect(bottom(leaping, 'run_pass')).toBeCloseTo(0, 6);
  });

  it("leaps with every committed figure's run frame furthest in the air", () => {
    const off = (doll: FigureManifest, name: string) => doll.frames[name].feet[1] - doll.frames[name].frame[3];
    for (const doll of Object.values(dolls)) {
      const name = shown(doll, 'jumping', 'east').frame;
      expect(doll.poses.run, doll.id).toContain(name);
      expect(off(doll, name), doll.id).toBe(Math.max(...doll.poses.run.map((run) => off(doll, run))));
      expect(bottom(doll, name), doll.id).toBeCloseTo(0, 6);
    }
  });

  it('lands standing, squashed by LANDING_SQUASH and springing back by the end', () => {
    expect(spritePose('landing', 'east')).toBe('land');
    expect(shown(figure, 'landing', 'east', 0)).toMatchObject({ pose: 'land', frame: 'stand', squash: LANDING_SQUASH });
    expect(shown(figure, 'landing', 'east', 0.5).squash).toBeCloseTo(LANDING_SQUASH / 2, 6);
    expect(shown(figure, 'landing', 'east', 0.999).squash).toBeCloseTo(0, 3);
  });

  it('plays painted jump and landing frames as they are', () => {
    const painted: FigureManifest = {
      ...figure,
      frames: { ...figure.frames, hop: frame(434, [30, 170]) },
      poses: { ...figure.poses, jump: ['hop'], land: ['stand'] },
    };
    expect(shown(painted, 'jumping', 'east').frame).toBe('hop');
    expect(shown(painted, 'jumping', 'east').bob).toBeCloseTo(0, 6);
    expect(shown(painted, 'landing', 'east', 0)).toMatchObject({ frame: 'stand', squash: 0 });
  });
});
