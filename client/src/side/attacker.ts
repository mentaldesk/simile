import type { Position } from '../net';
import { sideCreatures, type Tracked } from './creatures/creatures';

export const HIT_FROM_TILES = 3;

/** What hit the player at `at`: the nearest creature attacking within reach on their map, else the nearest there, never one going down. */
export function attackerOf(at: Position | undefined, creatures: Iterable<Tracked> = sideCreatures.all.values()): Tracked | undefined {
  if (!at) return undefined;
  let best: { creature: Tracked; distance: number; attacking: boolean } | undefined;
  for (const creature of creatures) {
    const distance = Math.hypot(at.x - creature.at.x, at.y - creature.at.y);
    if (creature.down !== undefined || creature.map !== (at.map ?? '') || distance > HIT_FROM_TILES) continue;
    const attacking = creature.state === 'attacking';
    if (!best || (attacking && !best.attacking) || (attacking === best.attacking && distance < best.distance)) {
      best = { creature, distance, attacking };
    }
  }
  return best?.creature;
}
