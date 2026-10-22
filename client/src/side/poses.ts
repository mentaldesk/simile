import type { Facing } from '../net';
import type { FigureManifest, SpritePose } from '../dolls/manifest';
import type { DollPose, PoseOptions } from '../dolls/rig';
import { facesLeft, shown, spritePose, type Shown } from '../dolls/sprite';
import { FURNITURE_DROP_M } from './layout';
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
 * or opening, where the street's props are left out too (`StreetView.ghost`). No one is drawn
 * see-through, and the player is always drawn. */
export const hiddenInFront = (inside: boolean, player: boolean, ghost: number): boolean =>
  !inside && !player && ghost < 1;

/** Metres up the front edge of each piece's seat is in its art: a stool's, a bench's plank, and a
 * cafe or noodle table's chairs. */
export const SEAT_M: Record<string, number> = { stool: 0.567, bench: 0.392, cafe_table: 0.442, noodle_table: 0.483 };
const SEATS = new Set(['seat', 'bar', 'desk']);

/** The seat at a map cell, on the piece under its spot as drawn, or a chair's where there's no
 * piece, or 0 off a seat. */
export function seatHeight(map: Pick<SideMap, 'spots' | 'furniture'>, x: number, y: number): number {
  const cx = Math.round(x);
  const cy = Math.round(y);
  if (!map.spots.some((s) => s.x === cx && s.y === cy && SEATS.has(s.type))) return 0;
  const piece = map.furniture.find(
    (f) => f.type in SEAT_M && cx >= f.x && cx < f.x + Math.max(1, f.w) && cy >= f.y && cy < f.y + Math.max(1, f.h),
  );
  return SEAT_M[piece?.type ?? 'cafe_table'] - FURNITURE_DROP_M;
}
