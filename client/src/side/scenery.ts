export type Rgb = [number, number, number];

export const TIMES = ['morning', 'afternoon', 'evening', 'night'] as const;
export type TimeName = (typeof TIMES)[number];

export const LAYERS = ['sky', 'far', 'mid', 'near', 'ground', 'foreground'] as const;
export type LayerName = (typeof LAYERS)[number];

export type Time = {
  tint: Rgb;
  sky: Rgb;
  /** The far layer's amount, then the colour, 0–255. */
  haze: [amount: number, r: number, g: number, b: number];
  glow: number;
};

export type PieceKind = 'sprite' | 'front' | 'glow' | 'layer' | 'strip' | 'ground' | 'paper';

export type Piece = {
  file: string;
  size: [number, number];
  /** Metres. */
  height: number;
  kind: PieceKind;
  anchor?: [number, number];
  /** Metres. */
  width?: number;
  eaves?: number;
};

export type BuildingEntry = { street: string; front: string; glow: string; floors: string[] };
export type FurnitureEntry = { piece: string; variants?: Record<string, string>; stretch?: boolean };

/** As content/papercraft/README.md describes it. */
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
