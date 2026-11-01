import Phaser from 'phaser';
import { isPlayerFigure, PLAYER_FIGURE } from '../dolls/bionics';
import type { FigureManifest } from '../dolls/manifest';
import type { Shown } from '../dolls/sprite';
import { SpriteFigure } from '../dolls/sprite-figure';
import { dollFor, playerBody } from '../world/assets';
import { DOLL_M, PPM } from './layout';
import type { Drawn } from './motion';
import { inBed, PoseCache, type Bed } from './poses';

/** A resident's painted figure, posed from a cache and tinted by the light; its origin is on the
 * ground under the middle of its head. The player's changes as bionics are fitted. */
export class SideDoll extends SpriteFigure {
  private cache: PoseCache;
  private tint = -1;
  private onSeat?: { from: Shown; seat: number; shown: Shown };
  private lain?: { figure: FigureManifest; bed: Bed; shown: Shown };

  constructor(scene: Phaser.Scene, figure: FigureManifest, key: string, height = DOLL_M * PPM) {
    super(scene, 0, 0, figure, key, height);
    this.cache = new PoseCache(figure);
    if (isPlayerFigure(figure.id)) {
      this.once(Phaser.GameObjects.Events.DESTROY, playerBody.onChange(() => this.follow()));
      if (dollFor(PLAYER_FIGURE) !== figure) this.follow();
    }
  }

  /** Wears the player's figure for what's fitted now. */
  private follow(): void {
    this.wear(dollFor(PLAYER_FIGURE)).catch((error: unknown) => console.warn(error));
  }

  /** Does nothing unless its frame, facing, seat, bed or tint changed. `seat` is how many metres up
   * the seat it sits on is, if it's sitting, and `bed` what it lies on, if it's in bed. */
  show(drawn: Drawn, tint: number, seat = 0, bed?: Bed): this {
    if (this.cache.figure !== this.figure) this.cache = new PoseCache(this.figure);
    if (drawn.bed > 0 && bed) this.draw(drawn.bed < 1 ? inBed(this.figure, bed, drawn.bed) : this.lying(bed));
    else {
      const { pose, facing, phase, seated, on, run } = drawn;
      const shown = this.cache.get(pose, facing, phase, seated, on, run);
      this.draw(shown.pose === 'sit' && seat > 0 ? this.seated(shown, seat) : shown);
    }
    if (tint !== this.tint) {
      this.tint = tint;
      this.setTint(tint);
    }
    return this;
  }

  private lying(bed: Bed): Shown {
    const last = this.lain;
    if (last?.figure === this.figure && last.bed === bed) return last.shown;
    this.lain = { figure: this.figure, bed, shown: inBed(this.figure, bed, 1) };
    return this.lain.shown;
  }

  private seated(from: Shown, seat: number): Shown {
    const last = this.onSeat;
    if (last?.from === from && last.seat === seat) return last.shown;
    this.onSeat = { from, seat, shown: { ...from, seat } };
    return this.onSeat.shown;
  }
}
