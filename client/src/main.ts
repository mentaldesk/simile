import Phaser from 'phaser';
import { collectScenes, type Area } from './areas';
import { fitZoom } from './world/view';

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

// Scrollbars would shrink the page the canvas is centred in, and take the canvas off-centre.
document.documentElement.style.overflow = 'hidden';

const fitCanvas = () => {
  if (game.isBooted) fitZoom(game.scale, game.scale.gameSize, window);
};
game.events.once(Phaser.Core.Events.READY, fitCanvas);
window.addEventListener('resize', fitCanvas);
