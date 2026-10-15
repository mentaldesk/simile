import Phaser from 'phaser';
import { collectScenes, type Area } from './areas';

new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'game',
  width: 640,
  height: 360,
  pixelArt: true,
  backgroundColor: '#1d2b26',
  scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
  scene: collectScenes(import.meta.glob<Area>('./*/index.ts', { eager: true })),
});
