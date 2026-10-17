import Phaser from 'phaser';
import { collectScenes, type Area } from './areas';
import { nativeCanvas } from './world/iso/canvas';
import { isoRequested } from './world/iso/controls';
import { fitZoom } from './world/view';

const iso = isoRequested(location.search);
const native = nativeCanvas(window);

// Phaser's RESIZE mode sizes the canvas in CSS pixels, so iso resizes it to device pixels itself.
const game = new Phaser.Game({
  type: Phaser.AUTO,
  parent: 'game',
  width: iso ? native.width : 640,
  height: iso ? native.height : 360,
  pixelArt: true,
  backgroundColor: '#1d2b26',
  scale: iso
    ? { mode: Phaser.Scale.NONE, autoCenter: Phaser.Scale.NO_CENTER, zoom: native.zoom }
    : { mode: Phaser.Scale.NONE, autoCenter: Phaser.Scale.CENTER_BOTH },
  scene: collectScenes(import.meta.glob<Area>('./*/index.ts', { eager: true })),
});

// Scrollbars would shrink the page the canvas is centred in, and take the canvas off-centre.
document.documentElement.style.overflow = 'hidden';

const fitCanvas = () => {
  if (game.isBooted) fitZoom(game.scale, game.scale.gameSize, window);
};

const fitNative = () => {
  const { width, height, zoom } = nativeCanvas(window);
  const { scale } = game;
  if (!game.isBooted || (width === scale.width && height === scale.height && zoom === scale.zoom)) {
    return;
  }
  scale.resize(width, height);
  scale.setZoom(zoom);
};

const fit = iso ? fitNative : fitCanvas;
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
if (iso) onPixelRatio();
