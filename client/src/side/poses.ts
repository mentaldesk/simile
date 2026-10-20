import type { Facing } from '../net';
import type { DollManifest } from '../dolls/manifest';
import { posed, type DollPose, type PoseOptions, type Posed } from '../dolls/rig';
import type { ClimbKind } from './maps';

/** Steps a cycle is cut into: the rig's poses are worked out once per step and kept. */
export const STEPS = 48;

const POSES: readonly DollPose[] = [
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
const POSE_INDEX = Object.fromEntries(POSES.map((pose, i) => [pose, i])) as Record<DollPose, number>;
const VIEW_FACINGS: readonly Facing[] = ['east', 'south', 'north'];
const OPTIONS: readonly PoseOptions[] = [{}, { seated: true }, { on: 'ladder' }, { on: 'stairs' }];

const viewIndex = (facing: Facing) => (facing === 'north' ? 2 : facing === 'south' ? 1 : 0);

/** Whether a facing draws the side view mirrored, facing left. */
export const facesLeft = (facing: Facing): boolean => facing.endsWith('west');

/** A doll's poses, each worked out the first time it's drawn: the rig allocates, this doesn't. */
export class PoseCache {
  private readonly doll: DollManifest;
  private readonly posed: (Posed | undefined)[] = [];

  constructor(doll: DollManifest) {
    this.doll = doll;
  }

  get(pose: DollPose, facing: Facing, phase: number, seated = false, on?: ClimbKind): Posed {
    const view = viewIndex(facing);
    const variant = seated ? 1 : on === 'ladder' ? 2 : on === 'stairs' ? 3 : 0;
    const cycle = phase - Math.floor(phase);
    const step = Math.min(STEPS - 1, Math.floor(cycle * STEPS));
    const index = ((POSE_INDEX[pose] * VIEW_FACINGS.length + view) * OPTIONS.length + variant) * STEPS + step;
    return (this.posed[index] ??= posed(this.doll, pose, VIEW_FACINGS[view], step / STEPS, OPTIONS[variant]));
  }

  get size(): number {
    return this.posed.filter(Boolean).length;
  }
}
