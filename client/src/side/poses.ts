import type { Facing } from '../net';
import type { FigureManifest, SpritePose } from '../dolls/manifest';
import type { DollPose, PoseOptions } from '../dolls/rig';
import { facesLeft, shown, spritePose, type Shown } from '../dolls/sprite';
import type { ClimbKind, SideMap } from './maps';

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

/** Whether a figure is left out: a resident on the street in front of a dollhouse that's open,
 * or opening, where the street's props fade (`StreetView.ghost`). No one is drawn see-through,
 * and the player is always drawn. */
export const hiddenInFront = (inside: boolean, player: boolean, ghost: number): boolean =>
  !inside && !player && ghost < 1;

/** Metres up a seat is: a stool's or a bar's, or a chair's, bench's or desk chair's. */
const SEAT_M = { high: 0.7, low: 0.45 };
const SEATS = new Set(['seat', 'desk', 'bar']);
const HIGH_SEATS = new Set(['stool', 'bar_stool']);

/** The seat at a map cell, by its spot and the furniture on it, or 0 where there's none. */
export function seatHeight(map: Pick<SideMap, 'spots' | 'furniture'>, x: number, y: number): number {
  const cx = Math.round(x);
  const cy = Math.round(y);
  const spot = map.spots.find((s) => s.x === cx && s.y === cy && SEATS.has(s.type));
  if (!spot) return 0;
  const under = map.furniture.find((f) => cx >= f.x && cx < f.x + Math.max(1, f.w) && cy >= f.y && cy < f.y + Math.max(1, f.h));
  return spot.type === 'bar' || (under && HIGH_SEATS.has(under.type)) ? SEAT_M.high : SEAT_M.low;
}
