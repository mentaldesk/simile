import type { LightMapInfo, SetLight } from './lighting';

/** `content/art/iso/scenery/<set>.json` or `interiors/<id>.json`: `server/simile/art/iso/README.md`. */
export type SceneryManifest = {
  format: number;
  set: string;
  hours: [start: number, end: number];
  sun: SetLight['sun'];
  tile: IsoTile & { metres: number };
  map: { id?: string; width: number; height: number };
  ground: {
    x: number;
    y: number;
    width: number;
    height: number;
    heights: Record<string, number>;
    chunks: GroundChunk[];
  };
  light_map: LightMapInfo;
  objects: SceneryObject[];
};

export type IsoTile = { width: number; height: number; px_per_metre_up: number };

export type GroundChunk = { image: string; x: number; y: number; width: number; height: number };

export type Slice = { x: number; width: number; depth: number };

export type SceneryObject = {
  id: string;
  kind: string;
  anchor: [x: number, y: number];
  footprint: [x0: number, y0: number, x1: number, y1: number];
  image: string;
  width: number;
  height: number;
  offset: [x: number, y: number];
  slices: Slice[];
  /** A frame's opening: its corners in px in its image, top left first and clockwise. */
  canvas?: [x: number, y: number][];
};

export const sceneryImages = (manifest: SceneryManifest): string[] => [
  ...manifest.ground.chunks.map(({ image }) => image),
  ...manifest.objects.map(({ image }) => image),
];
