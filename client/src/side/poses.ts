import type { Facing } from '../net';
import type { FigureManifest, SpritePose } from '../dolls/manifest';
import type { DollPose, PoseOptions } from '../dolls/rig';
import { facesLeft, shown, spritePose, type Shown } from '../dolls/sprite';
import type { ClimbKind } from './maps';

export { facesLeft };

/** Steps a cycle is cut into. */
export const STEPS = 48;

const KINDS: readonly SpritePose[] = ['stand', 'walk', 'run', 'sit', 'climb'];
const KIND_INDEX = Object.fromEntries(KINDS.map((kind, i) => [kind, i])) as Record<SpritePose, number>;
/** A pose and options each kind is drawn for. */
const AS: Record<SpritePose, [DollPose, PoseOptions]> = {
  stand: ['standing', {}],
  walk: ['walking', {}],
  run: ['walking', { run: 1 }],
  sit: ['sitting', {}],
  climb: ['climbing', { on: 'ladder' }],
};

/** Allocates nothing once each step of a pose has been drawn. */
export class PoseCache {
  private readonly figure: FigureManifest;
  private readonly shown: (Shown | undefined)[] = [];
  private readonly options: PoseOptions = {};

  constructor(figure: FigureManifest) {
    this.figure = figure;
  }

  /** `run` only turns `walking` into a run. */
  get(pose: DollPose, facing: Facing, phase: number, seated = false, on?: ClimbKind, run = 0): Shown {
    const { options } = this;
    options.seated = seated;
    options.on = on;
    options.run = run;
    const kind = spritePose(pose, facing, options);
    const left = facesLeft(facing) ? 1 : 0;
    const cycle = phase - Math.floor(phase);
    const step = Math.min(STEPS - 1, Math.floor(cycle * STEPS));
    const index = (KIND_INDEX[kind] * 2 + left) * STEPS + step;
    const [as, extra] = AS[kind];
    return (this.shown[index] ??= shown(this.figure, as, left ? 'west' : 'east', step / STEPS, extra));
  }

  get size(): number {
    return this.shown.filter(Boolean).length;
  }
}
