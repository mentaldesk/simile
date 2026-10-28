import { PPM } from './layout';

/** For the weakest hit and the strongest. */
export const BLOOD = {
  drops: { least: 3, most: 6 },
  radiusM: { least: 0.06, most: 0.085 },
} as const;
/** Metres above the feet the drops burst from. */
export const CHEST_M = 1.3;
export const LIFE_SECONDS = { least: 0.5, most: 0.8 };
const GRAVITY = 9.8 * PPM;
/** Metres a second: up, and along, away from what hit them. */
const LAUNCH = { up: { least: 1.2, most: 2.8 }, away: 0.9, spread: 1.6 };

const lerp = (range: { least: number; most: number }, t: number) => range.least + (range.most - range.least) * t;

/** In world px, y down. */
export type Drop = { x: number; y: number; vx: number; vy: number; radius: number; age: number; life: number; ground: number; landed: boolean };

export const alphaOf = ({ age, life }: Drop): number => Math.max(0, Math.min(1, 2 * (1 - age / life)));

export class Blood {
  readonly drops: Drop[] = [];

  /** `feet` and `ground`, the row under them while they're in the air, in world px; `away` 1 east or -1 west from what hit them, or 0. */
  burst(strength: number, feet: { x: number; y: number }, ground: number, away: number, random: () => number = Math.random): void {
    const count = Math.round(lerp(BLOOD.drops, strength));
    for (let i = 0; i < count; i++) {
      this.drops.push({
        x: feet.x + (random() - 0.5) * 0.2 * PPM,
        y: feet.y - CHEST_M * PPM + (random() - 0.5) * 0.3 * PPM,
        vx: (away * LAUNCH.away + (random() - 0.5) * LAUNCH.spread) * PPM,
        vy: -lerp(LAUNCH.up, random()) * PPM,
        radius: lerp(BLOOD.radiusM, random()) * (0.85 + 0.3 * strength) * PPM,
        age: 0,
        life: lerp(LIFE_SECONDS, random()),
        ground,
        landed: false,
      });
    }
  }

  clear(): void {
    this.drops.length = 0;
  }

  update(dt: number): void {
    for (const drop of this.drops) {
      drop.age += dt;
      if (drop.landed) continue;
      drop.vy += GRAVITY * dt;
      drop.x += drop.vx * dt;
      drop.y += drop.vy * dt;
      if (drop.y >= drop.ground) {
        drop.y = drop.ground;
        drop.vx = drop.vy = 0;
        drop.landed = true;
      }
    }
    for (let i = this.drops.length - 1; i >= 0; i--) if (this.drops[i].age >= this.drops[i].life) this.drops.splice(i, 1);
  }
}
