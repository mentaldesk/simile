/** A doll as the flat-doll route describes it: the creator's instant preview, posed by the rig.
 * Pixels are the atlas's. */
export type FlatDoll = {
  id?: string;
  /** Atlas pixels a unit; a standing doll is `height` units from sole to crown. */
  unit: number;
  height: number;
  /** The atlas. A URL or a data URL. */
  flat: string;
  painted?: string;
  pieces: Record<PieceName, PieceSpec>;
};

/** A character painted whole, as `content/dolls/<id>.json` and the doll job describe it. */
export type FigureManifest = {
  id?: string;
  /** False for someone who isn't a villager, like the clinic's doctor. */
  resident?: boolean;
  /** Atlas pixels a metre; a standing figure is `height` pixels from sole to crown. */
  ppm: number;
  height: number;
  /** No flat doll comes with a figure. */
  flat?: string;
  /** The atlas's URL. */
  painted?: string;
  frames: Record<string, SpriteFrame>;
  poses: Record<PaintedPose, string[]> & Partial<Record<SpritePose, string[]>>;
};

export type DollManifest = FlatDoll | FigureManifest;

export type SpriteFrame = {
  /** x, y, width and height in the atlas. */
  frame: [number, number, number, number];
  /** The ground under the middle of the head, from the frame's top-left. */
  feet: Point;
  /** Where a sitting figure sits, under the middle of its head. */
  seat?: Point;
};

/** What a figure is painted doing; every `DollPose` is drawn as one of them. */
export type SpritePose = PaintedPose | 'jump' | 'land';
/** What every figure has painted. Without a jump it jumps in its run's leap, and without a landing it lands standing. */
export type PaintedPose = 'stand' | 'walk' | 'run' | 'sit' | 'climb';

export const isFigure = (doll: DollManifest): doll is FigureManifest => 'frames' in doll;

export type Point = [number, number];

export type PieceSpec = {
  /** x, y, width and height in the atlas. */
  frame: [number, number, number, number];
  /** Where the piece turns, from its frame's top-left. */
  pivot: Point;
  joints: Record<string, Point>;
};

export const SIDE_PIECES = [
  'head',
  'torso',
  'upper_arm',
  'lower_arm',
  'upper_leg',
  'lower_leg',
  'shoe',
] as const;
export const STRAIGHT_PIECES = [
  'head_front',
  'torso_front',
  'head_back',
  'torso_back',
  'shoe_front',
] as const;
export const PIECES = [...SIDE_PIECES, ...STRAIGHT_PIECES] as const;

export type PieceName = (typeof PIECES)[number];
