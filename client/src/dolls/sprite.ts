import type { Facing } from '../net/protocol';
import type { FigureManifest, SpritePose } from './manifest';
import type { DollPose, PoseOptions } from './rig';

/** Of a standing figure's height, at the top of each step. */
export const WALK_BOB = 0.012;
/** Degrees each way, once a cycle. */
export const WALK_SWAY = 2;
export const LADDER_BOB = 0.015;

/** A frame of a figure as drawn: mirrored to face left, raised by `bob` of its height and turned
 * `sway` degrees clockwise about its feet. */
export type Shown = { pose: SpritePose; frame: string; flip: boolean; bob: number; sway: number };

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

/** Where a frame is drawn: its origin, as fractions of the frame, at the feet as drawn, mirrored
 * or not, `y` up by the bob in the figure's pixels, and turned `angle` degrees clockwise. */
export function placed(figure: FigureManifest, { frame, flip, bob, sway }: Shown) {
  const { frame: box, feet } = figure.frames[frame];
  const [, , w, h] = box;
  return {
    originX: (flip ? w - feet[0] : feet[0]) / w,
    originY: feet[1] / h,
    y: -bob * figure.height,
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
      };
    case 'climb':
      return { pose: kind, frame, flip: cycle >= 0.5, bob: LADDER_BOB * Math.abs(Math.sin(turn)), sway: 0 };
    default:
      return { pose: kind, frame, flip: facesLeft(facing), bob: 0, sway: 0 };
  }
}
