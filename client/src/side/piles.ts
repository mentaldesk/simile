import Phaser from 'phaser';
import type { Pile } from '../net';
import { DEPTH } from './depths';
import { feetOf, PPM, xOf } from './layout';
import type { Village } from './maps';

const RADIUS_M = 0.4;
const LIFT_M = 0.3;
const PULSE_S = 1.8;
const COLOUR = { cash: 0xffcf3a, things: 0x9fe8ff } as const;
const OUTLINE = 0x1b2430;

export type PileMark = { x: number; y: number; depth: number; cash: boolean };

/** Where to glint for each pile on the street shown or one of its floors, in world px. */
export function pileMarks(village: Village, street: string, piles: readonly Pile[]): PileMark[] {
  return piles.flatMap(({ at, items, money }) => {
    const map = village.map(at.map);
    if (map?.street !== street) return [];
    const depth = map.kind === 'street' ? DEPTH.streetFurniture + 0.5 : DEPTH.furniture + 0.25;
    const y = feetOf(map.offset.y + at.y) - LIFT_M * PPM;
    return [{ x: xOf(map.offset.x + at.x), y, depth, cash: !items.length && !!money }];
  });
}

/** A pulsing glint where something lies to pick up. */
export class PileGlints {
  private glints: Phaser.GameObjects.Graphics[] = [];
  private drawn?: { street: string; piles: readonly Pile[] };
  private readonly scene: Phaser.Scene;

  constructor(scene: Phaser.Scene) {
    this.scene = scene;
  }

  update(village: Village, street: string, piles: readonly Pile[], seconds: number): void {
    const same = this.drawn?.street === street && sameItems(this.drawn.piles, piles);
    if (!same) {
      this.destroy();
      this.glints = pileMarks(village, street, piles).map((mark) => this.glint(mark));
      this.drawn = { street, piles };
    }
    const alpha = 0.65 + 0.35 * Math.sin((seconds / PULSE_S) * Math.PI * 2);
    for (const glint of this.glints) glint.setAlpha(alpha);
  }

  destroy(): void {
    for (const glint of this.glints) glint.destroy();
    this.glints = [];
    this.drawn = undefined;
  }

  private glint({ x, y, depth, cash }: PileMark): Phaser.GameObjects.Graphics {
    const r = RADIUS_M * PPM;
    const star = [0, -r, r / 4, -r / 4, r, 0, r / 4, r / 4, 0, r, -r / 4, r / 4, -r, 0, -r / 4, -r / 4];
    const points = Array.from({ length: star.length / 2 }, (_, i) => new Phaser.Math.Vector2(star[i * 2], star[i * 2 + 1]));
    const colour = COLOUR[cash ? 'cash' : 'things'];
    return this.scene.add
      .graphics({ x, y })
      .fillStyle(colour, 0.3)
      .fillCircle(0, 0, r * 0.7)
      .fillStyle(colour, 1)
      .fillPoints(points, true)
      .lineStyle(r / 10, OUTLINE, 0.8)
      .strokePoints(points, true)
      .setDepth(depth);
  }
}

const itemsOf = ({ at, items, money }: Pile) => `${at.map}:${at.x},${at.y}:${items.map(({ id }) => id).join()}:${money ?? 0}`;

/** Whether two lists of piles lie in the same places and hold the same, as each `player_state` sends them anew. */
export const sameItems = (a: readonly Pile[], b: readonly Pile[]): boolean =>
  a.length === b.length && a.every((pile, i) => pile === b[i] || itemsOf(pile) === itemsOf(b[i]));
