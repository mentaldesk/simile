import type Phaser from 'phaser';
import type { FigureManifest } from '../dolls/manifest';
import { SpriteFigure } from '../dolls/sprite-figure';
import { DOLL_M, PPM } from './layout';
import type { Drawn } from './motion';
import { PoseCache } from './poses';

/** A resident's painted figure, posed from a cache and tinted by the light; its origin is on the
 * ground under the middle of its head. */
export class SideDoll extends SpriteFigure {
  private readonly cache: PoseCache;
  private tint = -1;

  constructor(scene: Phaser.Scene, figure: FigureManifest, key: string, height = DOLL_M * PPM) {
    super(scene, 0, 0, figure, key, height);
    this.cache = new PoseCache(figure);
  }

  /** Does nothing unless its frame, facing or tint changed. */
  show({ pose, facing, phase, seated, on, run }: Drawn, tint: number): this {
    this.draw(this.cache.get(pose, facing, phase, seated, on, run));
    if (tint !== this.tint) {
      this.tint = tint;
      this.setTint(tint);
    }
    return this;
  }
}
