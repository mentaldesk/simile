import type { Facing, Pose } from '../net/protocol';
import type { FlatDoll, PieceName, PieceSpec } from './manifest';

export type View = 'side' | 'front' | 'back';
/** The sim's poses, and the player's jump and landing. */
export type DollPose = Pose | 'jumping' | 'landing';

export type PoseOptions = {
  /** At a desk: `working` and `reading` sit instead of standing. */
  seated?: boolean;
  /** What `climbing` is on. By default a ladder from the back or front, stairs from the side. */
  on?: 'ladder' | 'stairs';
  /** How far `walking` has turned into a run, 0 to 1. */
  run?: number;
  /** Metres up the seat a sitting figure sits on is, over the point it's placed by. */
  seat?: number;
};

export type Placement = {
  piece: PieceName;
  /** Where the piece's pivot goes, in atlas pixels from the ground under the hips, y down. */
  x: number;
  y: number;
  /** Degrees clockwise, as Phaser turns. */
  angle: number;
  scaleY: number;
  /** 1, or less for a far limb, drawn darker. */
  shade: number;
};

/** The pieces back to front. A `flip`ped doll faces left: draw it mirrored. */
export type Posed = { view: View; flip: boolean; parts: Placement[] };

export const FAR = 0.8;

type Vec = { x: number; y: number };
type Pair = [number, number];

type SideAngles = {
  lean: number;
  nod: number;
  thigh: Pair;
  knee: Pair;
  foot: Pair;
  shoulder: Pair;
  elbow: Pair;
  plant: boolean;
  rise?: number;
  /** Units a planted pose is off the ground. */
  air?: number;
};

type StraightAngles = {
  /** Each pair is the picture's left, then right. Arms and legs swing outward. */
  arm: Pair;
  elbow: Pair;
  forearm: Pair;
  leg: Pair;
  thigh: Pair;
  knee: Pair;
  nod: number;
  arms: 'beside' | 'forward' | 'raised';
  plant: boolean;
  rise?: number;
  air?: number;
};

const TAU = Math.PI * 2;
const rad = (degrees: number) => (degrees * Math.PI) / 180;
const add = (a: Vec, b: Vec): Vec => ({ x: a.x + b.x, y: a.y + b.y });
const sub = (a: Vec, b: Vec): Vec => ({ x: a.x - b.x, y: a.y - b.y });
const pos = (v: number) => Math.max(0, v);
const mix = (a: number, b: number, w: number) => a + (b - a) * w;
const mixPair = (a: Pair, b: Pair, w: number): Pair => [mix(a[0], b[0], w), mix(a[1], b[1], w)];
/** Units off the ground at the top of a running stride. */
const RUN_AIR = 5;
/** Both feet off the ground while the legs are furthest apart, `air` units at most. */
const flight = (t: number, air: number) => (air * pos(Math.abs(Math.sin(t)) - 0.8)) / 0.2;

/** `v` swung by `degrees`: positive swings a hanging limb forward, to +x. */
function swing(v: Vec, degrees: number): Vec {
  const c = Math.cos(rad(degrees));
  const s = Math.sin(rad(degrees));
  return { x: v.x * c + v.y * s, y: -v.x * s + v.y * c };
}

function offset(spec: PieceSpec, joint: string, scaleY = 1): Vec {
  const at = spec.joints[joint];
  if (!at) throw new Error(`A doll piece has no ${joint} joint`);
  return { x: at[0] - spec.pivot[0], y: (at[1] - spec.pivot[1]) * scaleY };
}

export function viewOf(facing: Facing): { view: View; flip: boolean } {
  if (facing === 'north') return { view: 'back', flip: false };
  if (facing === 'south') return { view: 'front', flip: false };
  return { view: 'side', flip: facing.endsWith('west') };
}

const STAND: SideAngles = {
  lean: 0,
  nod: 0,
  thigh: [3, -3],
  knee: [0, 0],
  foot: [0, 0],
  shoulder: [4, -4],
  elbow: [8, 8],
  plant: true,
};

const SIT: Pick<SideAngles, 'thigh' | 'knee' | 'foot'> = {
  thigh: [86, 82],
  knee: [86, 82],
  foot: [0, 0],
};

function walk(phase: number, stride = 24, lift = 0, bend = 34): SideAngles {
  const t = TAU * phase;
  const leg = (t: number): [number, number, number] => {
    const thigh = stride * Math.sin(t) + lift;
    const knee = 8 + bend * pos(Math.sin(t + 1.9)) ** 1.5;
    const foot = -thigh + knee + (18 * pos(-Math.cos(t + 0.4)) - 6 * pos(Math.cos(t)));
    return [thigh, knee, lift ? -thigh + knee : foot];
  };
  const near = leg(t);
  const far = leg(t + Math.PI);
  return {
    lean: lift ? 8 : 3,
    nod: 2,
    thigh: [near[0], far[0]],
    knee: [near[1], far[1]],
    foot: [near[2], far[2]],
    shoulder: [-22 * Math.sin(t), 22 * Math.sin(t)],
    elbow: [14 + 10 * pos(-Math.sin(t)), 14 + 10 * pos(Math.sin(t))],
    plant: true,
  };
}

/** Leaning in, the knees high, the elbows bent and pumping, and off the ground between strides. */
function run(phase: number): SideAngles {
  const t = TAU * phase;
  const leg = (t: number): [number, number, number] => {
    const thigh = 10 + 32 * Math.sin(t);
    const stance = 30 * pos(-Math.cos(t)) ** 2;
    const knee = 16 + stance + 22 * pos(Math.sin(t)) + 90 * pos(Math.cos(t + 0.2)) ** 1.6;
    return [thigh, knee, 0.5 * (knee - thigh)];
  };
  const near = leg(t);
  const far = leg(t + Math.PI);
  return {
    lean: 13,
    nod: -8,
    thigh: [near[0], far[0]],
    knee: [near[1], far[1]],
    foot: [near[2], far[2]],
    shoulder: [10 - 40 * Math.sin(t), 10 + 40 * Math.sin(t)],
    elbow: [78 + 22 * pos(-Math.sin(t)), 78 + 22 * pos(Math.sin(t))],
    plant: true,
    air: flight(t, RUN_AIR),
  };
}

function blendSide(walking: SideAngles, running: SideAngles, w: number): SideAngles {
  if (w <= 0) return walking;
  if (w >= 1) return running;
  return {
    lean: mix(walking.lean, running.lean, w),
    nod: mix(walking.nod, running.nod, w),
    thigh: mixPair(walking.thigh, running.thigh, w),
    knee: mixPair(walking.knee, running.knee, w),
    foot: mixPair(walking.foot, running.foot, w),
    shoulder: mixPair(walking.shoulder, running.shoulder, w),
    elbow: mixPair(walking.elbow, running.elbow, w),
    plant: true,
    air: mix(walking.air ?? 0, running.air ?? 0, w),
  };
}

/** Up stairs: each foot lifted onto the next tread, under its knee. */
function stairs(phase: number): SideAngles {
  const t = TAU * phase;
  const leg = (t: number): [number, number, number] => {
    const thigh = 25 + 35 * Math.sin(t);
    const knee = Math.max(4, thigh + 8);
    return [thigh, knee, knee - thigh];
  };
  const near = leg(t);
  const far = leg(t + Math.PI);
  return {
    lean: 8,
    nod: 4,
    thigh: [near[0], far[0]],
    knee: [near[1], far[1]],
    foot: [near[2], far[2]],
    shoulder: [-18 * Math.sin(t), 18 * Math.sin(t)],
    elbow: [16, 16],
    plant: true,
  };
}

function sideAngles(pose: DollPose, phase: number, options: PoseOptions): SideAngles {
  const wave = Math.sin(TAU * phase);
  const legs = options.seated ? SIT : STAND;
  switch (pose) {
    case 'walking':
      return blendSide(walk(phase), run(phase), options.run ?? 0);
    case 'climbing':
      return options.on === 'ladder' ? ladderFromSide(phase) : stairs(phase);
    case 'sitting':
      return {
        ...STAND,
        ...SIT,
        lean: -3,
        shoulder: [22, 18],
        elbow: [38, 40],
      };
    case 'reading':
      return {
        ...STAND,
        ...legs,
        lean: 4,
        nod: 12,
        shoulder: [36, 30],
        elbow: [62 + 3 * wave, 60],
      };
    case 'working':
      return options.seated
        ? {
            ...STAND,
            ...SIT,
            lean: 6,
            nod: 8,
            shoulder: [34, 28],
            elbow: [56 + 6 * wave, 50],
          }
        : {
            ...STAND,
            lean: 3,
            nod: -4,
            shoulder: [70 + 28 * wave, 15],
            elbow: [30, 30],
          };
    case 'looking':
      return {
        ...STAND,
        nod: -14 + 2 * wave,
        shoulder: [-6, -2],
        elbow: [12, 12],
      };
    case 'riding':
      return { ...STAND, shoulder: [30, -4], elbow: [40, 8] };
    case 'jumping':
      return {
        lean: 10,
        nod: 0,
        thigh: [82, -38],
        knee: [105, 78],
        foot: [12, -25],
        shoulder: [105, -60],
        elbow: [15, 25],
        plant: false,
        rise: 10,
      };
    default:
      return STAND;
  }
}

function ladderFromSide(phase: number): SideAngles {
  const s = Math.sin(TAU * phase);
  return {
    lean: 4,
    nod: -6,
    thigh: [40 + 30 * s, 40 - 30 * s],
    knee: [70 + 30 * s, 70 - 30 * s],
    foot: [30 + 30 * s, 30 - 30 * s],
    shoulder: [150 - 20 * s, 150 + 20 * s],
    elbow: [30, 30],
    plant: false,
  };
}

const STRAIGHT: StraightAngles = {
  arm: [4, 4],
  elbow: [0, 0],
  forearm: [1, 1],
  leg: [1.5, 1.5],
  thigh: [1, 1],
  knee: [0, 0],
  nod: 0,
  arms: 'beside',
  plant: true,
};

function straightAngles(pose: DollPose, phase: number, options: PoseOptions): StraightAngles {
  const t = TAU * phase;
  const wave = Math.sin(t);
  const seated = {
    leg: [3, 3] as Pair,
    thigh: [0.3, 0.3] as Pair,
    knee: [0, 0] as Pair,
  };
  const legs = options.seated ? seated : {};
  switch (pose) {
    case 'walking': {
      const lift: Pair = [pos(Math.sin(t)), pos(-Math.sin(t))];
      const walking: StraightAngles = {
        ...STRAIGHT,
        arm: [5 + 4 * lift[1], 5 + 4 * lift[0]],
        elbow: [8 * lift[1], 8 * lift[0]],
        forearm: [1 - 0.15 * lift[1], 1 - 0.15 * lift[0]],
        thigh: [1 - 0.3 * lift[0], 1 - 0.3 * lift[1]],
      };
      const w = options.run ?? 0;
      if (w <= 0) return walking;
      const stance: Pair = [pos(-Math.cos(t)) ** 2, pos(Math.cos(t)) ** 2];
      const swing: Pair = [pos(Math.cos(t + 0.2)) ** 1.6, pos(-Math.cos(t + 0.2)) ** 1.6];
      const running: StraightAngles = {
        ...STRAIGHT,
        arm: [14 + 6 * lift[1], 14 + 6 * lift[0]],
        elbow: [35 + 105 * lift[1], 35 + 105 * lift[0]],
        forearm: [0.7 - 0.25 * lift[1], 0.7 - 0.25 * lift[0]],
        leg: [2.5, 2.5],
        thigh: [1 - 0.55 * swing[0] - 0.12 * stance[0], 1 - 0.55 * swing[1] - 0.12 * stance[1]],
        knee: [4 * swing[0], 4 * swing[1]],
        nod: -3,
        air: flight(t, RUN_AIR),
      };
      return w >= 1 ? running : blendStraight(walking, running, w);
    }
    case 'climbing':
      return options.on === 'stairs' ? straightAngles('walking', phase, {}) : ladder(phase);
    case 'sitting':
      return {
        ...STRAIGHT,
        ...seated,
        arm: [10, 10],
        elbow: [40, 40],
        forearm: [0.8, 0.8],
      };
    case 'reading':
      return {
        ...STRAIGHT,
        ...legs,
        arm: [14, 14],
        elbow: [105 + 4 * wave, 105],
        forearm: [0.75, 0.75],
        nod: 10,
        arms: 'forward',
      };
    case 'working':
      return {
        ...STRAIGHT,
        ...legs,
        arm: [18, 16],
        elbow: [95 + 14 * Math.sin(2 * t), 95 - 14 * Math.sin(2 * t)],
        forearm: [0.7, 0.7],
        nod: 6,
        arms: 'forward',
      };
    case 'looking':
      return { ...STRAIGHT, nod: -14 + 2 * wave };
    case 'jumping':
      return {
        ...STRAIGHT,
        arm: [140, 140],
        elbow: [20, 20],
        thigh: [0.65, 0.65],
        leg: [8, 8],
        knee: [-10, -10],
        arms: 'raised',
        plant: false,
        rise: 10,
      };
    default:
      return STRAIGHT;
  }
}

function blendStraight(walking: StraightAngles, running: StraightAngles, w: number): StraightAngles {
  return {
    ...walking,
    arm: mixPair(walking.arm, running.arm, w),
    elbow: mixPair(walking.elbow, running.elbow, w),
    forearm: mixPair(walking.forearm, running.forearm, w),
    leg: mixPair(walking.leg, running.leg, w),
    thigh: mixPair(walking.thigh, running.thigh, w),
    knee: mixPair(walking.knee, running.knee, w),
    nod: mix(walking.nod, running.nod, w),
    air: mix(walking.air ?? 0, running.air ?? 0, w),
  };
}

function ladder(phase: number): StraightAngles {
  const s = Math.sin(TAU * phase);
  return {
    ...STRAIGHT,
    arm: [160 + 15 * s, 160 - 15 * s],
    elbow: [-25 + 15 * s, -25 - 15 * s],
    leg: [4, 4],
    thigh: [1 - 0.45 * pos(s), 1 - 0.45 * pos(-s)],
    arms: 'raised',
    plant: false,
  };
}

type Put = (piece: PieceName, at: Vec, turn: number, shade?: number, scaleY?: number) => void;

function placer(parts: Placement[]): Put {
  return (piece, at, turn, shade = 1, scaleY = 1) =>
    parts.push({ piece, x: at.x, y: at.y, angle: -turn, scaleY, shade });
}

function placeSide(doll: FlatDoll, a: SideAngles): Placement[] {
  const p = doll.pieces;
  const parts: Placement[] = [];
  const put = placer(parts);
  const hip = { x: 0, y: 0 };
  const torso = -a.lean;
  const torsoAt = sub(hip, swing(offset(p.torso, 'hip'), torso));
  const neck = add(torsoAt, swing(offset(p.torso, 'neck'), torso));
  const shoulder = add(torsoAt, swing(offset(p.torso, 'shoulder'), torso));
  const leg = (i: 0 | 1, shade: number) => {
    const thigh = a.thigh[i];
    const shin = thigh - a.knee[i];
    const knee = add(hip, swing(offset(p.upper_leg, 'knee'), thigh));
    const ankle = add(knee, swing(offset(p.lower_leg, 'ankle'), shin));
    put('upper_leg', hip, thigh, shade);
    put('lower_leg', knee, shin, shade);
    put('shoe', ankle, shin + a.foot[i], shade);
  };
  const arm = (i: 0 | 1, shade: number) => {
    const upper = torso + a.shoulder[i];
    const elbow = add(shoulder, swing(offset(p.upper_arm, 'elbow'), upper));
    put('upper_arm', shoulder, upper, shade);
    put('lower_arm', elbow, upper + a.elbow[i], shade);
  };
  arm(1, FAR);
  leg(1, FAR);
  leg(0, 1);
  put('torso', torsoAt, torso);
  put('head', neck, torso - a.nod);
  arm(0, 1);
  return parts;
}

function placeStraight(doll: FlatDoll, view: 'front' | 'back', a: StraightAngles): Placement[] {
  const p = doll.pieces;
  const torso = p[view === 'front' ? 'torso_front' : 'torso_back'];
  const legs: Placement[] = [];
  const uppers: Placement[] = [];
  const forearms: Placement[] = [];
  const at = { x: 0, y: 0 };
  ([-1, 1] as const).forEach((side, i) => {
    const name = side < 0 ? 'left' : 'right';
    const hip = add(at, offset(torso, `hip_${name}`));
    const thigh = side * a.leg[i];
    const knee = add(hip, swing(offset(p.upper_leg, 'knee', a.thigh[i]), thigh));
    const shin = thigh + side * a.knee[i];
    const ankle = add(knee, swing(offset(p.lower_leg, 'ankle'), shin));
    placer(legs)('upper_leg', hip, thigh, 1, a.thigh[i]);
    placer(legs)('lower_leg', knee, shin);
    placer(legs)('shoe_front', ankle, 0);
    const shoulder = add(at, offset(torso, `shoulder_${name}`));
    const upper = side * a.arm[i];
    const elbow = add(shoulder, swing(offset(p.upper_arm, 'elbow'), upper));
    placer(uppers)('upper_arm', shoulder, upper);
    placer(forearms)('lower_arm', elbow, upper - side * a.elbow[i], 1, a.forearm[i]);
  });
  const body: Placement[] = [];
  placer(body)(view === 'front' ? 'torso_front' : 'torso_back', at, 0);
  const head: Placement[] = [];
  const nod = { x: 0, y: a.nod * 0.06 * doll.unit };
  placer(head)(
    view === 'front' ? 'head_front' : 'head_back',
    add(add(at, offset(torso, 'neck')), nod),
    0,
  );
  if (a.arms === 'raised') return [...legs, ...body, ...head, ...uppers, ...forearms];
  if (a.arms === 'forward' && view === 'back')
    return [...legs, ...forearms, ...body, ...uppers, ...head];
  return [...legs, ...body, ...uppers, ...forearms, ...head];
}

/** The lowest point of the posed pieces' frames, in atlas pixels. */
export function lowest(doll: FlatDoll, parts: Placement[]): number {
  let low = -Infinity;
  for (const part of parts) {
    const spec = doll.pieces[part.piece];
    const [, , w, h] = spec.frame;
    for (const [cx, cy] of [
      [0, 0],
      [w, 0],
      [0, h],
      [w, h],
    ]) {
      const corner = {
        x: cx - spec.pivot[0],
        y: (cy - spec.pivot[1]) * part.scaleY,
      };
      low = Math.max(low, part.y + swing(corner, -part.angle).y);
    }
  }
  return low;
}

function angles(pose: DollPose, view: View, phase: number, options: PoseOptions) {
  const on = options.on ?? (view === 'side' ? 'stairs' : 'ladder');
  return view === 'side'
    ? sideAngles(pose, phase, { ...options, on })
    : straightAngles(pose, phase, { ...options, on });
}

function place(doll: FlatDoll, view: View, a: SideAngles | StraightAngles): Placement[] {
  return view === 'side'
    ? placeSide(doll, a as SideAngles)
    : placeStraight(doll, view, a as StraightAngles);
}

/** Every piece placed for `pose`, facing `facing`, `phase` of the way through its cycle. Planted
 * poses stand on the ground (y = 0); the rest keep the standing hip height, so a ladder climb
 * or a jump moves only as its caller moves it. */
export function posed(
  doll: FlatDoll,
  pose: DollPose,
  facing: Facing,
  phase = 0,
  options: PoseOptions = {},
): Posed {
  const { view, flip } = viewOf(facing);
  const cycle = phase - Math.floor(phase);
  const a = angles(pose, view, cycle, options);
  const parts = place(doll, view, a);
  const ground = a.plant
    ? lowest(doll, parts) + (a.air ?? 0) * doll.unit
    : lowest(doll, place(doll, view, angles('standing', view, 0, {}))) + (a.rise ?? 0) * doll.unit;
  return {
    view,
    flip,
    parts: parts.map((part) => ({ ...part, y: part.y - ground })),
  };
}

/** Atlas pixels from the ground to the top of a standing doll's head, hair and hats included. */
export function standingHeight(doll: FlatDoll): number {
  const { parts } = posed(doll, 'standing', 'south');
  const head = parts.find((part) => part.piece === 'head_front');
  if (!head) throw new Error('A standing doll has a head');
  return -(head.y - doll.pieces.head_front.pivot[1]);
}
