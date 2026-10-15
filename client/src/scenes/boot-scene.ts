import Phaser from 'phaser';
import {
  characters,
  FACINGS,
  MAP_KEY,
  TILES_KEY,
  tilesUrl,
  village,
  WALK_FPS,
  walkAnimation,
  walkFrames,
} from '../world';
import { WORLD_SCENE } from './world-scene';

const harnessOpen = () => {
  const params = new URLSearchParams(location.search);
  return import.meta.env.DEV && (params.has('harness') || params.has('audio-harness'));
};

export class BootScene extends Phaser.Scene {
  constructor() {
    super('boot');
  }

  preload(): void {
    this.load.image(TILES_KEY, tilesUrl);
    this.load.tilemapTiledJSON(MAP_KEY, village);
    for (const { key, image, atlas } of characters) this.load.atlas(key, image, atlas);
  }

  create(): void {
    for (const { key } of characters) {
      for (const facing of FACINGS) {
        this.anims.create({
          key: walkAnimation(key, facing),
          frames: walkFrames(facing).map((frame) => ({ key, frame })),
          frameRate: WALK_FPS,
          repeat: -1,
        });
      }
    }
    // The dev harnesses set up their own world view and positions.
    if (!harnessOpen()) this.scene.start(WORLD_SCENE);
  }
}
