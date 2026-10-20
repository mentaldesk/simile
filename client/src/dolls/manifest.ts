/** A doll as `content/dolls/<id>.json` and the flat-doll route describe it. Pixels are the atlas's. */
export type DollManifest = {
  id?: string;
  /** Atlas pixels a unit; a standing doll is `height` units from sole to crown. */
  unit: number;
  height: number;
  /** The flat atlas, drawn at once, and the painted one that replaces it. URLs or data URLs. */
  flat: string;
  painted?: string;
  pieces: Record<PieceName, PieceSpec>;
};

export type Point = [number, number];

export type PieceSpec = {
  /** x, y, width and height in the atlas. Both atlases share it. */
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
