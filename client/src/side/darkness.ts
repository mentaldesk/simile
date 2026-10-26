import type { Item, Position } from '../net';
import { interactableAt } from '../world/interactables';
import { mapOf } from '../world/map';
import { LOW, shining } from './lamp';
import type { SideMap } from './maps';

/** The darkness over a dark cell never seen, as an alpha. */
export const DARK = 0.95;
/** Over one seen by the lamp before but not lit now. */
export const DIM = 0.65;
/** Tiles to the edge of a full lamp's light. */
export const LAMP_RADIUS = 4.5;
/** The share of the radius lit fully, fading to nothing at its edge. */
export const INNER = 0.45;
/** Below `LOW` charge the light draws in, to this share of its radius when flat. */
export const FADED = 0.55;
/** Cells above the feet the lamp is held: 1.2 m. */
export const LAMP_HEIGHT = 1.1;
/** Without the lamp, just enough to make out the player. */
export const GLIMMER = { radius: 1.2, strength: 0.4 };
/** The infrared eye without the lamp: the dark around the player seen through a red veil. */
export const EYE = { radius: 5, strength: 0.6 };

/** Light around a point in street cells, where cell (x, y) spans x to x + 1. */
export type Glow = { x: number; y: number; radius: number; strength: number; infrared?: boolean };

export function isLit(map: SideMap, x: number, y: number): boolean {
  let dark = false;
  for (const area of map.light) {
    if (x < area.x || y < area.y || x >= area.x + area.w || y >= area.y + area.h) continue;
    if (area.props.lit === true) return true;
    dark = true;
  }
  return !dark;
}

export const hasDark = (map: SideMap): boolean => map.light.some(({ props }) => props.lit !== true);

export function lampRadius(charge: number): number {
  const low = Math.min(Math.max(charge, 0) / LOW, 1);
  return LAMP_RADIUS * (FADED + (1 - FADED) * low);
}

/** Whether the player stands at a plug, as the server reads it: on one of its stand tiles. */
export const atPlug = (position: Position | undefined): boolean =>
  !!position && interactableAt(mapOf(position), position)?.kind === 'plug';

/** The lamp's light around the player at `at`, in street cells, else the eye's sight or a glimmer. */
export function glowAround(at: { x: number; y: number }, lamp: Item | undefined, eye = false): Glow {
  const x = at.x + 0.5;
  const y = at.y + 1 - LAMP_HEIGHT;
  if (shining(lamp)) return { x, y, radius: lampRadius(lamp!.charge ?? 0), strength: 1 };
  return eye ? { x, y, ...EYE, infrared: true } : { x, y, ...GLIMMER };
}

/** The share of the darkness a glow takes away at `distance`. */
export function falloff(distance: number, radius: number): number {
  const t = distance / radius;
  if (t <= INNER) return 1;
  return t >= 1 ? 0 : (1 - t) / (1 - INNER);
}

/** The dark cells of a street the player has seen by their lamp, kept while the page is open. */
export class Sight {
  readonly map: SideMap;
  readonly seen: Uint8Array;
  private readonly dark: Uint8Array;

  constructor(map: SideMap) {
    this.map = map;
    this.seen = new Uint8Array(map.width * map.height);
    this.dark = new Uint8Array(map.width * map.height);
    for (let y = 0; y < map.height; y++) {
      for (let x = 0; x < map.width; x++) this.dark[y * map.width + x] = isLit(map, x, y) ? 0 : 1;
    }
  }

  /** Marks the dark cells the lamp lights or the eye sees as seen. Whether any were new. */
  see(glow: Glow): boolean {
    if (glow.strength < 1 && !glow.infrared) return false;
    const { width, height } = this.map;
    const reach = glow.radius * (1 + INNER) * 0.5;
    let found = false;
    for (let y = Math.max(0, Math.floor(glow.y - reach)); y < Math.min(height, Math.ceil(glow.y + reach)); y++) {
      for (let x = Math.max(0, Math.floor(glow.x - reach)); x < Math.min(width, Math.ceil(glow.x + reach)); x++) {
        const i = y * width + x;
        if (!this.dark[i] || this.seen[i] || Math.hypot(x + 0.5 - glow.x, y + 0.5 - glow.y) > reach) continue;
        this.seen[i] = 1;
        found = true;
      }
    }
    return found;
  }

  /** The darkness over a cell by itself: none where it's lit, `DIM` once seen, else `DARK`. */
  shade(x: number, y: number): number {
    const i = y * this.map.width + x;
    if (!this.dark[i]) return 0;
    return this.seen[i] ? DIM : DARK;
  }

  /** The darkness drawn over a cell, with `glow` around the player. */
  darkness(x: number, y: number, glow?: Glow): number {
    const shade = this.shade(x, y);
    if (!glow || !shade) return shade;
    const distance = Math.hypot(x + 0.5 - glow.x, y + 0.5 - glow.y);
    return shade * (1 - glow.strength * falloff(distance, glow.radius));
  }
}

const sights = new Map<string, Sight>();

/** Each street's, made on first use. */
export function sightOf(map: SideMap): Sight {
  let sight = sights.get(map.id);
  if (!sight || sight.map !== map) sights.set(map.id, (sight = new Sight(map)));
  return sight;
}
