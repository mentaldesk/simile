import type { Rgb, SetLight } from './lighting';
import type { IsoTile, SceneryObject } from './manifest';

type Footprint = SceneryObject['footprint'];
import { project } from './projection';
import type { LightingSet } from './time-of-day';

/** An interior's one lighting set. */
export const INSIDE = 'inside';

export type SceneSet = LightingSet | typeof INSIDE;

export type Sun = SetLight['sun'];

/** The interiors' key light: `INSIDE` in `server/simile/art/iso/lighting.py`. */
export const INSIDE_SUN: Sun = { azimuth: 160, elevation: 60 };

/** Neutral, so the room's light map gives residents its colour, and dim enough to show its pools. */
export const INSIDE_TINT: Rgb = [0.6, 0.6, 0.6];
/** Softer than outside: the interiors' key light is broad and high. */
export const INSIDE_SHADOW_STRENGTH = 0.45;

/** A figure's drop shadow under a sun, worked out as `lights.json` is from `lighting.py`. */
export function sunShadow(
  { azimuth, elevation }: Sun,
  figureTiles: number,
  tile: IsoTile,
): Omit<SetLight['shadow'], 'strength'> {
  const [a, e] = [azimuth, elevation].map((degrees) => (degrees * Math.PI) / 180);
  const direction: [number, number] = [-Math.sin(a), Math.cos(a)];
  const length = figureTiles / Math.tan(e);
  const tip = project(tile, { x: direction[0] * length, y: direction[1] * length });
  return { direction, length, tip: [tip.x, tip.y] };
}

/** Residents' light indoors, which `lights.json` doesn't have. */
export function insideLight(sun: Sun, figureTiles: number, tile: IsoTile): SetLight {
  return {
    sun,
    tint: INSIDE_TINT,
    shadow: { strength: INSIDE_SHADOW_STRENGTH, ...sunShadow(sun, figureTiles, tile) },
  };
}

/** What can hide the player and fades out when it does: buildings, and the gallery's partitions. */
export const cutawaysOf = (objects: readonly SceneryObject[]): SceneryObject[] =>
  objects.filter(({ id, kind }) => kind === 'building' || (kind === 'wall' && id.startsWith('partition-')));

const touching = ([ax0, ay0, ax1, ay1]: Footprint, [bx0, by0, bx1, by1]: Footprint) =>
  ax0 < bx1 && ax1 > bx0 && ay0 <= by1 && ay1 >= by0;

/** The frames hanging on a wall, which fade with it. */
export const framesOn = (wall: SceneryObject, objects: readonly SceneryObject[]): SceneryObject[] =>
  objects.filter(({ kind, footprint }) => kind === 'frame' && touching(footprint, wall.footprint));
