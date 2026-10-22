import Phaser from 'phaser';
import { isPlayerFigure, PLAYER_FIGURE } from '../dolls/bionics';
import type { FigureManifest } from '../dolls/manifest';
import type { Shown } from '../dolls/sprite';
import { SpriteFigure } from '../dolls/sprite-figure';
import { dollFor, playerBody } from '../world/assets';
import { DOLL_M, PPM } from './layout';
import type { Drawn } from './motion';
import { PoseCache } from './poses';

/** A resident's painted figure, posed from a cache and tinted by the light; its origin is on the
 * ground under the middle of its head. The player's changes as bionics are fitted. */
export class SideDoll extends SpriteFigure {
  private cache: PoseCache;
  private tint = -1;
  private onSeat?: { from: Shown; seat: number; shown: Shown };

  constructor(scene: Phaser.Scene, figure: FigureManifest, key: string, height = DOLL_M * PPM) {
    super(scene, 0, 0, figure, key, height);
    this.cache = new PoseCache(figure);
    if (isPlayerFigure(figure.id)) {
      const stop = playerBody.onChange(() => void this.wear(dollFor(PLAYER_FIGURE)));
      this.once(Phaser.GameObjects.Events.DESTROY, stop);
    }
  }

  /** Does nothing unless its frame, facing, seat or tint changed. `seat` is how many metres up
   * the seat it sits on is, if it's sitting. */
  show({ pose, facing, phase, seated, on, run }: Drawn, tint: number, seat = 0): this {
    if (this.cache.figure !== this.figure) this.cache = new PoseCache(this.figure);
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
