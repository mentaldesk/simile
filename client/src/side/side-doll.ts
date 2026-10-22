import type Phaser from 'phaser';
import type { FigureManifest } from '../dolls/manifest';
import type { Shown } from '../dolls/sprite';
import { SpriteFigure } from '../dolls/sprite-figure';
import { DOLL_M, PPM } from './layout';
import type { Drawn } from './motion';
import { PoseCache } from './poses';

/** A resident's painted figure, posed from a cache and tinted by the light; its origin is on the
 * ground under the middle of its head. */
export class SideDoll extends SpriteFigure {
  private readonly cache: PoseCache;
  private tint = -1;
  private onSeat?: { from: Shown; seat: number; shown: Shown };

  constructor(scene: Phaser.Scene, figure: FigureManifest, key: string, height = DOLL_M * PPM) {
    super(scene, 0, 0, figure, key, height);
    this.cache = new PoseCache(figure);
  }

  /** Does nothing unless its frame, facing, seat or tint changed. `seat` is how many metres up
   * the seat it sits on is, if it's sitting. */
  show({ pose, facing, phase, seated, on, run }: Drawn, tint: number, seat = 0): this {
    const shown = this.cache.get(pose, facing, phase, seated, on, run);
    this.draw(shown.pose === 'sit' && seat > 0 ? this.seated(shown, seat) : shown);
    if (tint !== this.tint) {
      this.tint = tint;
      this.setTint(tint);
    }
    return this;
  }

  private seated(from: Shown, seat: number): Shown {
    const last = this.onSeat;
    if (last?.from === from && last.seat === seat) return last.shown;
    this.onSeat = { from, seat, shown: { ...from, seat } };
    return this.onSeat.shown;
  }
}
