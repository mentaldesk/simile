import type { CreatureState } from '../net';
import type { Hit } from '../ui/hurt';
import { sideCreatures } from './creatures/creatures';
import type { SidePlayer } from './player';

export const FLINCH_SECONDS = { least: 0.35, most: 0.75 };
/** Times a second the figure turns red and back while it flinches. */
export const BLINK_HZ = 12;
/** Tiles a second they're knocked away and up, y down, for the weakest hit and the strongest. */
export const KNOCK = { vx: { least: 2.5, most: 5 }, vy: { least: -3, most: -5.5 } };
/** Tiles within which a creature is taken to be what hit them. */
export const HIT_FROM_TILES = 3;

const lerp = (range: { least: number; most: number }, t: number) => range.least + (range.most - range.least) * t;

type Placed = { x: number; y: number; map: string };
type Near = { at: { x: number; y: number }; map: string; state: CreatureState; down?: number };

/** 1 east or -1 west: away from the nearest creature attacking them, else the nearest, else back from the way they face. */
export function awayFrom(player: Placed, facing: string, creatures: Iterable<Near>): 1 | -1 {
  let from: { gap: number; distance: number; attacking: boolean } | undefined;
  for (const { at, map, state, down } of creatures) {
    const gap = player.x - at.x;
    const distance = Math.hypot(gap, player.y - at.y);
    if (down !== undefined || map !== player.map || distance > HIT_FROM_TILES || gap === 0) continue;
    const attacking = state === 'attacking';
    if (!from || (attacking && !from.attacking) || (attacking === from.attacking && distance < from.distance)) {
      from = { gap, distance, attacking };
    }
  }
  if (from) return from.gap > 0 ? 1 : -1;
  return facing === 'west' ? 1 : -1;
}

export const knockOf = (strength: number): { vx: number; vy: number } => ({
  vx: lerp(KNOCK.vx, strength),
  vy: lerp(KNOCK.vy, strength),
});

/** Red over the light's tint, keeping its brightness. */
export function reddened(tint: number): number {
  const r = (tint >> 16) & 0xff;
  const g = (tint >> 8) & 0xff;
  const b = tint & 0xff;
  const bright = Math.max(r, g, b);
  return (bright << 16) | (Math.round(bright * 0.2) << 8) | Math.round(bright * 0.2);
}

/** The player's figure flinching from a hit: knocked back a little, blinking red for longer the harder it was. */
export class Flinch {
  private left = 0;
  private seconds = 0;

  /** Knocks `player` away from what hit them, if they're on their feet. */
  hit({ strength }: Hit, player?: SidePlayer): void {
    this.seconds = 0;
    this.left = Math.max(this.left, lerp(FLINCH_SECONDS, strength));
    if (!player) return;
    const away = awayFrom(player.mapPosition, player.facing, sideCreatures.all.values());
    const { vx, vy } = knockOf(strength);
    player.knock(away * vx, vy);
  }

  update(dt: number): void {
    this.seconds += dt;
    this.left = Math.max(this.left - dt, 0);
  }

  /** The figure's tint under `light`: red on every other blink while it flinches. */
  tint(light: number): number {
    const red = this.left > 0 && Math.floor(this.seconds * BLINK_HZ * 2) % 2 === 0;
    return red ? reddened(light) : light;
  }
}
