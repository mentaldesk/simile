import type { Facing } from '../net/protocol';
import type { FigureManifest, SpritePose } from './manifest';
import type { DollPose, PoseOptions } from './rig';

/** Of a standing figure's height, at the top of each step. */
export const WALK_BOB = 0.012;
/** Degrees each way, once a cycle. */
export const WALK_SWAY = 2;
export const LADDER_BOB = 0.015;
/** Of its height a landing figure is squashed at first, springing back over the landing. */
export const LANDING_SQUASH = 0.1;

/** A frame of a figure as drawn: mirrored to face left, raised by `bob` of its height and turned
 * `sway` degrees clockwise about its feet, or sitting on a seat or lying on a bed `seat` metres up. */
export type Shown = {
  pose: SpritePose;
  frame: string;
  flip: boolean;
  bob: number;
  sway: number;
  seat: number;
  /** Of its height, landing. */
  squash?: number;
  /** Metres to the right. */
  shift?: number;
};

export const facesLeft = (facing: Facing): boolean => facing.endsWith('west');

const sideways = (facing: Facing) => facing !== 'north' && facing !== 'south';

/** What each of the sim's poses is drawn as. Facing north or south shows the three-quarter
 * figure, as Paper Mario does, but a ladder shows the climb from behind. */
export function spritePose(pose: DollPose, facing: Facing, options: PoseOptions = {}): SpritePose {
  switch (pose) {
    case 'walking':
      return (options.run ?? 0) >= 0.5 ? 'run' : 'walk';
    case 'jumping':
      return 'jump';
    case 'landing':
      return 'land';
    case 'sitting':
      return 'sit';
    case 'sleeping':
      return 'lie';
    case 'reading':
    case 'working':
      return options.seated ? 'sit' : 'stand';
    case 'climbing':
      return (options.on ?? (sideways(facing) ? 'stairs' : 'ladder')) === 'stairs' ? 'walk' : 'climb';
    default:
      return 'stand';
  }
}

/** Where a frame is drawn: its origin as fractions of the frame, its offset in figure pixels and its angle. */
export function placed(figure: FigureManifest, { pose, frame, flip, bob, sway, seat, shift = 0 }: Shown) {
  const { frame: box, feet, seat: sits, bed } = figure.frames[frame];
  const [, , w, h] = box;
  const along = shift * figure.ppm;
  if (pose === 'lie') {
    const y = -seat * figure.ppm;
    if (bed) return { originX: bed[0] / w, originY: bed[1] / h, x: along, y, angle: sway };
    return { originX: 0, originY: feet[1] / 2 / h, x: along, y, angle: sway - 90 };
  }
  const [x, y] = seat > 0 && sits ? sits : feet;
  return {
    originX: (flip ? w - x : x) / w,
    originY: y / h,
    x: along,
    y: -bob * figure.height - (seat > 0 && sits ? seat * figure.ppm : 0),
    angle: flip ? -sway : sway,
  };
}

/** The frame `phase` of the way through the pose's cycle, any number. */
export function shown(
  figure: FigureManifest,
  pose: DollPose,
  facing: Facing,
  phase = 0,
  options: PoseOptions = {},
): Shown {
  const kind = spritePose(pose, facing, options);
  const frames = framesOf(figure, kind);
  const cycle = phase - Math.floor(phase);
  const frame = frames[Math.min(frames.length - 1, Math.floor(cycle * frames.length))];
  const turn = 2 * Math.PI * cycle;
  switch (kind) {
    case 'walk':
      return {
        pose: kind,
        frame,
        flip: facesLeft(facing),
        bob: (WALK_BOB * (1 - Math.cos(2 * (turn - Math.PI / 4)))) / 2,
        sway: WALK_SWAY * Math.sin(turn),
        seat: 0,
      };
    case 'climb':
      return { pose: kind, frame, flip: cycle >= 0.5, bob: LADDER_BOB * Math.abs(Math.sin(turn)), sway: 0, seat: 0 };
    case 'sit':
      return { pose: kind, frame, flip: facesLeft(facing), bob: 0, sway: 0, seat: options.seat ?? 0 };
    case 'jump':
      return { pose: kind, frame, flip: facesLeft(facing), bob: lift(figure, frame), sway: 0, seat: 0 };
    case 'lie':
      return { pose: kind, frame, flip: false, bob: 0, sway: 0, seat: options.seat ?? 0 };
    case 'land': {
      const squash = figure.poses.land?.length ? 0 : LANDING_SQUASH * (1 - cycle);
      return { pose: kind, frame, flip: facesLeft(facing), bob: 0, sway: 0, seat: 0, squash };
    }
    default:
      return { pose: kind, frame, flip: facesLeft(facing), bob: 0, sway: 0, seat: 0 };
  }
}

/** A pose's painted frames: a jump without its own is the run's leap, and anything else missing stands. */
function framesOf(figure: FigureManifest, kind: SpritePose): readonly string[] {
  const painted = figure.poses[kind];
  if (painted?.length) return painted;
  return kind === 'jump' ? [leap(figure)] : figure.poses.stand;
}

/** The run's frame furthest off the ground. */
export function leap(figure: FigureManifest): string {
  const off = (name: string) => lift(figure, name);
  return figure.poses.run.reduce((best, name) => (off(name) < off(best) ? name : best), figure.poses.run[0]);
}

/** How far to raise a frame so its lowest point is on the ground: below 0 for a frame drawn in the air. */
function lift(figure: FigureManifest, frame: string): number {
  const { frame: box, feet } = figure.frames[frame];
  return (feet[1] - box[3]) / -figure.height;
}
