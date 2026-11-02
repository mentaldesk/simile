export type Rgb = [number, number, number];

export const TIMES = ['morning', 'afternoon', 'evening', 'night'] as const;
export type TimeName = (typeof TIMES)[number];

export const LAYERS = ['sky', 'far', 'mid', 'near', 'ground', 'foreground'] as const;
export type LayerName = (typeof LAYERS)[number];
/** The city sits between the sky and the far layer, and streets underground leave it out. */
type Layers<T> = Record<LayerName, T> & { city?: T };

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
  /** Ground pieces: metres down from the strip's top to the far edge of the walking surface. */
  surface?: number;
};

export type BuildingEntry = { street: string; front: string; glow: string; floors: string[] };
export type Moulding = { left: number; right: number; top: number; bottom: number };
export type FurnitureEntry = {
  piece: string;
  variants?: Record<string, string>;
  stretch?: boolean;
  /** Metres up the front edge. */
  seat?: number;
  /** Metres up the front edge. */
  bed?: number;
  /** Metres up the lamp's head. */
  light?: number;
  /** The frame picture's px. */
  moulding?: Moulding;
};
/** `at`: street id to a fraction of its width. */
export type Landmark = { piece: string; glow: string; at: Record<string, number> };

/** As content/papercraft/README.md describes it. */
export type SceneryManifest = {
  version: number;
  ppm: number;
  parallax: Layers<number>;
  times: Record<TimeName, Time>;
  streets: Record<string, Layers<string>>;
  landmarks?: Record<string, Landmark>;
  grounds: Record<string, string>;
  buildings: Record<string, BuildingEntry>;
  furniture: Record<string, FurnitureEntry>;
  platforms: Record<string, string>;
  slab: string;
  pieces: Record<string, Piece>;
};
