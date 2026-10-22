import Phaser from 'phaser';
import { DEPTH } from './depths';
import { INNER, type Glow, type Sight } from './darkness';
import { TILE } from './layout';

/** Canvas px a cell: the lamp's edge stays soft once scaled up. */
const RES = 4;
const NIGHT: [number, number, number] = [5, 7, 14];

/** Darkness over a street's dark stretches, dimmed where the lamp has been and cut away around the player. */
export class DarkView {
  private readonly scene: Phaser.Scene;
  private readonly sight: Sight;
  private readonly key: string;
  private readonly texture: Phaser.Textures.CanvasTexture;
  private readonly image: Phaser.GameObjects.Image;
  private readonly base: HTMLCanvasElement;
  private drawn = '';

  constructor(scene: Phaser.Scene, sight: Sight) {
    this.scene = scene;
    this.sight = sight;
    const { id, width, height } = sight.map;
    this.key = `side:dark:${id}`;
    this.texture = scene.textures.createCanvas(this.key, width * RES, height * RES)!;
    this.base = Object.assign(document.createElement('canvas'), { width, height });
    this.paintBase();
    this.image = scene.add.image(0, 0, this.key).setOrigin(0, 0).setDepth(DEPTH.dark);
    this.image.setDisplaySize(width * TILE, height * TILE);
  }

  update(glow: Glow): void {
    if (this.sight.see(glow)) {
      this.paintBase();
      this.drawn = '';
    }
    const signature = `${glow.x.toFixed(3)},${glow.y.toFixed(3)},${glow.radius.toFixed(3)},${glow.strength}`;
    if (signature === this.drawn) return;
    this.drawn = signature;
    const { context, width, height } = this.texture;
    context.clearRect(0, 0, width, height);
    context.imageSmoothingEnabled = true;
    context.drawImage(this.base, 0, 0, width, height);
    context.globalCompositeOperation = 'destination-out';
    const [x, y, radius] = [glow.x * RES, glow.y * RES, glow.radius * RES];
    const light = context.createRadialGradient(x, y, 0, x, y, radius);
    light.addColorStop(0, `rgba(0, 0, 0, ${glow.strength})`);
    light.addColorStop(INNER, `rgba(0, 0, 0, ${glow.strength})`);
    light.addColorStop(1, 'rgba(0, 0, 0, 0)');
    context.fillStyle = light;
    context.fillRect(x - radius, y - radius, 2 * radius, 2 * radius);
    context.globalCompositeOperation = 'source-over';
    this.texture.refresh();
  }

  destroy(): void {
    this.image.destroy();
    this.scene.textures.remove(this.key);
  }

  private paintBase(): void {
    const { width, height } = this.base;
    const context = this.base.getContext('2d')!;
    const cells = context.createImageData(width, height);
    for (let y = 0; y < height; y++) {
      for (let x = 0; x < width; x++) {
        const i = 4 * (y * width + x);
        cells.data.set(NIGHT, i);
        cells.data[i + 3] = Math.round(this.sight.shade(x, y) * 255);
      }
    }
    context.putImageData(cells, 0, 0);
  }
}
