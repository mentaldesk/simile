import Phaser from 'phaser';
import { collectScenes, type Area } from './areas';
import { pixelZoom } from './world/view';

const game = new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'game',
  width: 640,
  height: 360,
  pixelArt: true,
  backgroundColor: '#1d2b26',
  scale: { mode: Phaser.Scale.NONE, autoCenter: Phaser.Scale.CENTER_BOTH },
  scene: collectScenes(import.meta.glob<Area>('./*/index.ts', { eager: true })),
});

const fitCanvas = () => {
  const zoom = pixelZoom(game.scale.parentSize, game.scale.gameSize, window.devicePixelRatio);
  if (zoom !== game.scale.zoom) game.scale.setZoom(zoom);
};
game.events.once(Phaser.Core.Events.READY, fitCanvas);
game.scale.on(Phaser.Scale.Events.RESIZE, fitCanvas);
