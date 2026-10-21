import type { Facing } from '../net';
import type { DollManifest } from '../dolls/manifest';
import { posed, type DollPose, type PoseOptions, type Posed } from '../dolls/rig';
import type { ClimbKind } from './maps';

/** Steps a cycle is cut into. */
export const STEPS = 48;
/** Steps from a walk to a run. */
export const RUN_STEPS = 8;

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
const OPTIONS: readonly PoseOptions[] = [
  {},
  { seated: true },
  { on: 'ladder' },
  { on: 'stairs' },
  ...Array.from({ length: RUN_STEPS }, (_, i) => ({ run: (i + 1) / RUN_STEPS })),
];

const viewIndex = (facing: Facing) => (facing === 'north' ? 2 : facing === 'south' ? 1 : 0);

export const facesLeft = (facing: Facing): boolean => facing.endsWith('west');

/** The rig allocates; a cached pose doesn't. */
export class PoseCache {
  private readonly doll: DollManifest;
  private readonly posed: (Posed | undefined)[] = [];

  constructor(doll: DollManifest) {
    this.doll = doll;
  }

  /** `run` only turns `walking` into a run. */
  get(pose: DollPose, facing: Facing, phase: number, seated = false, on?: ClimbKind, run = 0): Posed {
    const view = viewIndex(facing);
    const blend = pose === 'walking' ? Math.round(run * RUN_STEPS) : 0;
    const variant = blend > 0 ? 3 + blend : seated ? 1 : on === 'ladder' ? 2 : on === 'stairs' ? 3 : 0;
    const cycle = phase - Math.floor(phase);
    const step = Math.min(STEPS - 1, Math.floor(cycle * STEPS));
    const index = ((POSE_INDEX[pose] * VIEW_FACINGS.length + view) * OPTIONS.length + variant) * STEPS + step;
    return (this.posed[index] ??= posed(this.doll, pose, VIEW_FACINGS[view], step / STEPS, OPTIONS[variant]));
  }

  get size(): number {
    return this.posed.filter(Boolean).length;
  }
}
