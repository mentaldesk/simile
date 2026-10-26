import type { CreatureKind, CreatureState, SideFacing } from '../../net';
import { DOWN_SECONDS, type Tracked } from './creatures';

/** `content/creatures/<kind>.json`: README.md there. */
export type CreatureManifest = {
  id: CreatureKind;
  ppm: number;
  moves: 'walk' | 'fly';
  /** Its first frame's width and height in metres. */
  size: [number, number];
  painted: string;
  frames: Record<string, CreatureFrame>;
  poses: Record<string, string[]>;
};

export type CreatureFrame = {
  /** x, y, width and height in the atlas. */
  frame: [number, number, number, number];
  /** Where the creature is, from the frame's top-left. */
  anchor: [number, number];
  hangs?: boolean;
};

const manifests = import.meta.glob<CreatureManifest>('../../../../content/creatures/*.json', {
  eager: true,
  import: 'default',
});
const atlases = import.meta.glob<string>('../../../../content/creatures/*.webp', {
  eager: true,
  query: '?url',
  import: 'default',
});

const folder = (path: string) => path.slice(0, path.lastIndexOf('/') + 1);

export const creatureFigures: Partial<Record<CreatureKind, CreatureManifest>> = Object.fromEntries(
  Object.entries(manifests).map(([path, figure]) => [figure.id, { ...figure, painted: atlases[folder(path) + figure.painted] }]),
);

/** Its kind's cycle, whichever it has: rats and bots walk, dogs run and bats fly. */
const CYCLES = ['walk', 'run', 'fly'];
/** Metres a walking cycle moves on each frame, as a share of the creature's length. */
const STRIDE_SHARE = 0.45;
/** Seconds each frame of a pose played on the spot is shown. */
const FRAME_SECONDS: Record<string, number> = { fly: 0.09, attack: 0.15 };
const STILL_FRAME_SECONDS = 0.3;
/** The share of the tile it sinks while going down, flying or not. */
const DOWN_DROP = { walk: 0.05, fly: 0.6 };

/** The pose `docs/protocol.md`'s table gives a state. */
export function poseOf(figure: CreatureManifest, state: CreatureState): string {
  const { poses } = figure;
  const cycle = CYCLES.find((pose) => poses[pose]) ?? Object.keys(poses)[0];
  const still = poses.stand ? 'stand' : cycle;
  switch (state) {
    case 'moving':
    case 'chasing':
    case 'fleeing':
      return cycle;
    case 'attacking':
      return poses.attack ? 'attack' : still;
    case 'roosting':
      return poses.roost ? 'roost' : still;
    default:
      return still;
  }
}

/** A walking cycle steps with the distance covered, anything else with time. */
export function frameOf(figure: CreatureManifest, tracked: Tracked): string {
  const pose = poseOf(figure, tracked.state);
  const frames = figure.poses[pose];
  const walking = pose !== 'fly' && CYCLES.includes(pose);
  const step = walking
    ? tracked.travelled / (figure.size[0] * STRIDE_SHARE)
    : tracked.seconds / (FRAME_SECONDS[pose] ?? STILL_FRAME_SECONDS);
  return frames[Math.floor(step) % frames.length];
}

export type Placed = { originX: number; originY: number; flip: boolean };

/** Its anchor as the frame's origin, mirrored about the anchor to face west. */
export function placedOf(figure: CreatureManifest, frame: string, facing: SideFacing): Placed {
  const {
    frame: [, , w, h],
    anchor: [x, y],
  } = figure.frames[frame];
  const flip = facing === 'west';
  return { originX: (flip ? w - x : x) / w, originY: y / h, flip };
}

export type Going = { angle: number; alpha: number; drop: number };

/** Keeling over on its back and fading; `drop` is in tiles. */
export function goingDown(figure: CreatureManifest, facing: SideFacing, down: number): Going {
  const t = Math.min(down / DOWN_SECONDS, 1);
  const eased = 1 - (1 - t) ** 2;
  return {
    angle: (facing === 'west' ? 90 : -90) * eased,
    alpha: 1 - t * t,
    drop: DOWN_DROP[figure.moves] * eased,
  };
}
