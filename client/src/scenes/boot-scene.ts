import Phaser from 'phaser';
import { characters } from '../world';
import { ISO_SCENE } from './iso-scene';

const harnessOpen = () => {
  const params = new URLSearchParams(location.search);
  return import.meta.env.DEV && (params.has('harness') || params.has('audio-harness'));
};

export class BootScene extends Phaser.Scene {
  constructor() {
    super('boot');
  }

  preload(): void {
    for (const { key, image, atlas } of characters) this.load.atlas(key, image, atlas);
  }

  create(): void {
    // The dev harnesses set up their own world view and positions.
    if (!harnessOpen()) this.scene.start(ISO_SCENE);
  }
}
