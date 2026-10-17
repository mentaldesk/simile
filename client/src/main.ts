import Phaser from 'phaser';
import { collectScenes, type Area } from './areas';
import { nativeCanvas } from './world/iso/canvas';

const native = nativeCanvas(window);

// Phaser's RESIZE mode sizes the canvas in CSS pixels, so this resizes it to device pixels itself.
const game = new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'game',
  width: native.width,
  height: native.height,
  pixelArt: true,
  backgroundColor: '#1d2b26',
  scale: { mode: Phaser.Scale.NONE, autoCenter: Phaser.Scale.NO_CENTER, zoom: native.zoom },
  scene: collectScenes(import.meta.glob<Area>('./*/index.ts', { eager: true })),
});

document.documentElement.style.overflow = 'hidden';

const fit = () => {
  const { width, height, zoom } = nativeCanvas(window);
  const { scale } = game;
  if (!game.isBooted || (width === scale.width && height === scale.height && zoom === scale.zoom)) {
    return;
  }
  scale.resize(width, height);
  scale.setZoom(zoom);
};

game.events.once(Phaser.Core.Events.READY, fit);
window.addEventListener('resize', fit);

// Moving the window to a screen with another pixel ratio needn't resize it.
const onPixelRatio = () =>
  matchMedia(`(resolution: ${window.devicePixelRatio}dppx)`).addEventListener(
    'change',
    () => {
      fit();
      onPixelRatio();
    },
    { once: true },
  );
onPixelRatio();
