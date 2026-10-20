/** content/papercraft/manifest.json, as content/papercraft/README.md describes it. */
export type Rgb = [number, number, number];

export const TIMES = ['morning', 'afternoon', 'evening', 'night'] as const;
export type TimeName = (typeof TIMES)[number];

export const LAYERS = ['sky', 'far', 'mid', 'near', 'ground', 'foreground'] as const;
export type LayerName = (typeof LAYERS)[number];

export type Time = {
  /** Multiplies near layers and sprites. */
  tint: Rgb;
  sky: Rgb;
  /** How far the far layer goes to the colour (0–255), the mid layer half as far. */
  haze: [amount: number, r: number, g: number, b: number];
  /** How strongly the glow maps add. */
  glow: number;
};

export type PieceKind = 'sprite' | 'front' | 'glow' | 'layer' | 'strip' | 'ground' | 'paper';

export type Piece = {
  file: string;
  size: [number, number];
  /** Metres tall. */
  height: number;
  kind: PieceKind;
  anchor?: [number, number];
  /** A front's walls, in metres. */
  width?: number;
  eaves?: number;
};

export type BuildingEntry = { street: string; front: string; glow: string; floors: string[] };
export type FurnitureEntry = { piece: string; variants?: Record<string, string>; stretch?: boolean };

export type SceneryManifest = {
  version: number;
  ppm: number;
  parallax: Record<LayerName, number>;
  times: Record<TimeName, Time>;
  streets: Record<string, Record<LayerName, string>>;
  grounds: Record<string, string>;
  buildings: Record<string, BuildingEntry>;
  furniture: Record<string, FurnitureEntry>;
  platforms: Record<string, string>;
  slab: string;
  pieces: Record<string, Piece>;
};
