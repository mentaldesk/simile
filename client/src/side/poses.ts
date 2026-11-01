import type { Facing } from '../net';
import type { FigureManifest, SpritePose } from '../dolls/manifest';
import type { DollPose, PoseOptions } from '../dolls/rig';
import { facesLeft, shown, spritePose, type Shown } from '../dolls/sprite';
import { FURNITURE_DROP_M, TILE_M } from './layout';
import type { ClimbKind, SideMap } from './maps';

export { facesLeft };

/** Steps a cycle is cut into. */
export const STEPS = 48;

const KINDS: readonly SpritePose[] = ['stand', 'walk', 'run', 'sit', 'climb', 'jump', 'land', 'lie'];
const KIND_INDEX = Object.fromEntries(KINDS.map((kind, i) => [kind, i])) as Record<SpritePose, number>;
/** A pose and options each kind is drawn for. */
const AS: Record<SpritePose, [DollPose, PoseOptions]> = {
  stand: ['standing', {}],
  walk: ['walking', {}],
  run: ['walking', { run: 1 }],
  sit: ['sitting', {}],
  climb: ['climbing', { on: 'ladder' }],
  jump: ['jumping', {}],
  land: ['landing', {}],
  lie: ['sleeping', {}],
};

/** Allocates nothing once each step of a pose has been drawn. */
export class PoseCache {
  readonly figure: FigureManifest;
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

/** A resident on the street in front of an open dollhouse is left out; the player never is. */
export const hiddenInFront = (inside: boolean, player: boolean, ghost: number): boolean =>
  !inside && !player && ghost < 1;

/** Metres up the front edge of each piece's seat, measured from its art. */
export const SEAT_M: Record<string, number> = { stool: 0.567, bench: 0.392, cafe_table: 0.442, noodle_table: 0.483 };
const SEATS = new Set(['seat', 'bar', 'desk']);

/** Metres up the seat at a map cell as drawn: its piece's, a chair's without one, or 0 off a seat. */
export function seatHeight(map: Pick<SideMap, 'spots' | 'furniture'>, x: number, y: number): number {
  const cx = Math.round(x);
  const cy = Math.round(y);
  if (!map.spots.some((s) => s.x === cx && s.y === cy && SEATS.has(s.type))) return 0;
  const piece = map.furniture.find(
    (f) => f.type in SEAT_M && cx >= f.x && cx < f.x + Math.max(1, f.w) && cy >= f.y && cy < f.y + Math.max(1, f.h),
  );
  return SEAT_M[piece?.type ?? 'cafe_table'] - FURNITURE_DROP_M;
}

/** Metres up the front edge of the bed's mattress, measured from its art. */
export const BED_M = 0.45;
/** Lying down, or getting up. */
export const LIE_SECONDS = 0.8;
/** Degrees a figure lying down starts with its head raised, or getting up ends. */
const LIE_TILT = 25;

/** What a figure lies on: metres up as drawn, and metres right from its cell's middle to the middle of the piece. */
export type Bed = { height: number; along: number };

const FLOOR: Bed = { height: 0, along: 0 };
const beds = new WeakMap<object, Map<number, Bed>>();

/** The bed whose piece is under a map cell, or the floor. */
export function bedAt(map: Pick<SideMap, 'furniture'>, x: number, y: number): Bed {
  const cx = Math.round(x);
  const cy = Math.round(y);
  let known = beds.get(map);
  if (!known) beds.set(map, (known = new Map()));
  const key = cy * 4096 + cx;
  let bed = known.get(key);
  if (!bed) {
    const piece = map.furniture.find(
      (f) => f.type === 'bed' && cx >= f.x && cx < f.x + Math.max(1, f.w) && cy >= f.y && cy < f.y + Math.max(1, f.h),
    );
    bed = piece ? { height: BED_M - FURNITURE_DROP_M, along: (piece.x + piece.w / 2 - cx - 0.5) * TILE_M } : FLOOR;
    known.set(key, bed);
  }
  return bed;
}

/** How far into bed a figure is after `dt` more seconds of lying down, or of getting up. */
export const settle = (inBed: number, lying: boolean, dt: number): number =>
  Math.min(1, Math.max(0, inBed + ((lying ? 1 : -1) * dt) / LIE_SECONDS));

const ease = (t: number): number => t * t * (3 - 2 * t);
const between = (a: number, b: number, t: number): number => a + (b - a) * t;

/** A figure `progress` of the way from standing by a bed to lying on it, sitting on its edge first. */
export function inBed(figure: FigureManifest, bed: Bed, progress: number): Shown {
  if (progress < 0.5) {
    const frame = figure.poses.sit[0];
    const { feet, seat } = figure.frames[frame];
    const natural = seat ? (feet[1] - seat[1]) / figure.ppm : 0;
    const height = bed.height > 0 ? bed.height : natural;
    const t = ease(progress / 0.5);
    const shift = (bed.along / 2) * t;
    return { pose: 'sit', frame, flip: false, bob: 0, sway: 0, seat: between(natural, height, t), shift };
  }
  const t = ease((progress - 0.5) / 0.5);
  const frame = figure.poses.lie?.[0] ?? figure.poses.stand[0];
  const shift = (bed.along / 2) * (1 + t);
  return { pose: 'lie', frame, flip: false, bob: 0, sway: LIE_TILT * (1 - t), seat: bed.height, shift };
}
