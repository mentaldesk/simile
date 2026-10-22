import type { Facing } from '../net/protocol';
import type { FigureManifest, SpritePose } from './manifest';
import type { DollPose, PoseOptions } from './rig';

/** Of a standing figure's height, at the top of each step. */
export const WALK_BOB = 0.012;
/** Degrees each way, once a cycle. */
export const WALK_SWAY = 2;
export const LADDER_BOB = 0.015;

/** A frame of a figure as drawn: mirrored to face left, raised by `bob` of its height and turned
 * `sway` degrees clockwise about its feet, or sitting on a seat `seat` metres up. */
export type Shown = { pose: SpritePose; frame: string; flip: boolean; bob: number; sway: number; seat: number };

export const facesLeft = (facing: Facing): boolean => facing.endsWith('west');

const sideways = (facing: Facing) => facing !== 'north' && facing !== 'south';

/** What each of the sim's poses is drawn as. Facing north or south shows the three-quarter
 * figure, as Paper Mario does, but a ladder shows the climb from behind. */
export function spritePose(pose: DollPose, facing: Facing, options: PoseOptions = {}): SpritePose {
  switch (pose) {
    case 'walking':
      return (options.run ?? 0) >= 0.5 ? 'run' : 'walk';
    case 'jumping':
      return 'run';
    case 'sitting':
      return 'sit';
    case 'reading':
    case 'working':
      return options.seated ? 'sit' : 'stand';
    case 'climbing':
      return (options.on ?? (sideways(facing) ? 'stairs' : 'ladder')) === 'stairs' ? 'walk' : 'climb';
    default:
      return 'stand';
  }
}

/** Where a frame is drawn: its origin, as fractions of the frame, at the feet as drawn, or on a
 * seat where it sits, mirrored or not; `y` up by the bob or the seat, in the figure's pixels;
 * and turned `angle` degrees clockwise. */
export function placed(figure: FigureManifest, { frame, flip, bob, sway, seat }: Shown) {
  const { frame: box, feet, seat: sits } = figure.frames[frame];
  const [, , w, h] = box;
  const [x, y] = seat > 0 && sits ? sits : feet;
  return {
    originX: (flip ? w - x : x) / w,
    originY: y / h,
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
  const frames = figure.poses[kind]?.length ? figure.poses[kind] : figure.poses.stand;
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
    default:
      return { pose: kind, frame, flip: facesLeft(facing), bob: 0, sway: 0, seat: 0 };
  }
}
