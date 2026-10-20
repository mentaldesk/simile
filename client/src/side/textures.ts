import Phaser from 'phaser';
import { stretchParts } from './layout';

const PREFIX = 'side:';
const SHADOW = '#1e140c';
const TILE_FRAME = 'tile';
/** Alpha above which a column of a tiling picture counts as drawn. */
const OPAQUE = 8;

/** A picture made from another: its texture `key`, its `name` to make more from, and the scale
 * and padding it was drawn at, to scale it back up. */
export type Derived = { key: string; name: string; scale: number; pad: number };

function canvasOf(width: number, height: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.ceil(width));
  canvas.height = Math.max(1, Math.ceil(height));
  const context = canvas.getContext('2d')!;
  context.imageSmoothingQuality = 'high';
  return [canvas, context];
}

/** The scene's own pictures, each filtered smoothly though the game is set for pixel art, and
 * the silhouettes, light maps and stretched runs made from them, each made once. */
export class SideTextures {
  private readonly scene: Phaser.Scene;
  private readonly loading = new Map<string, Promise<string>>();
  private readonly derived = new Map<string, Derived>();

  constructor(scene: Phaser.Scene) {
    this.scene = scene;
  }

  /** Loads a picture once under `key`, resolving to its texture key. */
  load(key: string, url: string): Promise<string> {
    const texture = PREFIX + key;
    let loading = this.loading.get(texture);
    if (!loading) {
      loading = (async () => {
        const image = new Image();
        image.src = url;
        await image.decode();
        if (!this.scene.textures.exists(texture)) this.add(texture, image);
        return texture;
      })();
      this.loading.set(texture, loading);
    }
    return loading;
  }

  key(key: string): string {
    return PREFIX + key;
  }

  /** A blurred, dark silhouette of a loaded picture at `scale` of its size, from its alpha. */
  shadow(key: string, scale: number, blur: number): Derived {
    return this.make(`${key}#shadow${scale}`, key, (source, context, pad) => {
      context.filter = `blur(${blur}px)`;
      context.drawImage(source, pad, pad, source.width * scale, source.height * scale);
      context.filter = 'none';
      context.globalCompositeOperation = 'source-in';
      context.fillStyle = SHADOW;
      context.fillRect(0, 0, context.canvas.width, context.canvas.height);
    }, scale, Math.ceil(blur * 2.5));
  }

  /** A light map at `scale`, blurred by `blur` px for its bloom, or sharp. */
  light(key: string, scale: number, blur = 0): Derived {
    return this.make(`${key}#light${scale}x${blur}`, key, (source, context, pad) => {
      context.fillStyle = '#000';
      context.fillRect(0, 0, context.canvas.width, context.canvas.height);
      if (blur) context.filter = `blur(${blur}px)`;
      context.drawImage(source, pad, pad, source.width * scale, source.height * scale);
    }, scale, Math.ceil(blur * 2.5));
  }

  /** A picture blurred where it is: the out-of-focus foreground. */
  blurred(key: string, blur: number): Derived {
    return this.make(`${key}#blur${blur}`, key, (source, context, pad) => {
      context.filter = `blur(${blur}px)`;
      context.drawImage(source, pad, pad);
    }, 1, 0);
  }

  /** A run `width` px wide: the picture's ends kept and its middle repeated between them. */
  stretched(key: string, width: number): Derived {
    return this.make(`${key}@${width}`, key, (source, context) => {
      const { end, middle, repeats } = stretchParts(width, source.width);
      const h = source.height;
      for (let i = 0; i < repeats; i++) {
        context.drawImage(source, end, 0, middle, h, end + i * middle, 0, middle, h);
      }
      context.clearRect(width - end, 0, end, h);
      context.drawImage(source, 0, 0, end, h, 0, 0, end, h);
      context.drawImage(source, source.width - end, 0, end, h, width - end, 0, end, h);
    }, 1, 0, width);
  }

  /** A picture repeated along a band `width` by `height` px, scaled to the band's height. */
  band(key: string, width: number, height: number): Derived {
    return this.make(`${key}#band${width}x${height}`, key, (source, context) => {
      const step = (source.width * height) / source.height;
      for (let x = 0; x < width; x += step) context.drawImage(source, x, 0, step, height);
    }, height / this.source(key).height, 0, width);
  }

  /** Black, more opaque towards the top and the sides: a room's back wall in shadow under its
   * ceiling and in its corners. */
  roomShade(): string {
    const key = `${PREFIX}room-shade`;
    if (this.scene.textures.exists(key)) return key;
    const size = 64;
    const [canvas, context] = canvasOf(size, size);
    const pixels = context.createImageData(size, size);
    const clip = (v: number) => Math.min(Math.max(v, 0), 1);
    for (let y = 0; y < size; y++) {
      for (let x = 0; x < size; x++) {
        const [u, v] = [(x + 0.5) / size, (y + 0.5) / size];
        const lit = (0.72 + 0.28 * clip(v / 0.35)) * (0.88 + 0.12 * clip(Math.min(u, 1 - u) / 0.12));
        pixels.data[(y * size + x) * 4 + 3] = Math.round((1 - lit) * 255);
      }
    }
    context.putImageData(pixels, 0, 0);
    this.add(key, canvas);
    return key;
  }

  /** A frame of a tiling picture without the empty columns at its ends, so its copies meet
   * edge to edge: some of #309's strips start with a transparent margin. */
  tileFrame(key: string): { frame: string; x: number; width: number } {
    const texture = this.scene.textures.get(PREFIX + key);
    if (texture.has(TILE_FRAME)) {
      const known = texture.get(TILE_FRAME);
      return { frame: TILE_FRAME, x: known.cutX, width: known.cutWidth };
    }
    const source = this.source(key);
    const [, context] = canvasOf(source.width, source.height);
    context.drawImage(source, 0, 0);
    const { data } = context.getImageData(0, 0, source.width, source.height);
    const opaque = (x: number) => {
      for (let y = 0; y < source.height; y++) if (data[(y * source.width + x) * 4 + 3] > OPAQUE) return true;
      return false;
    };
    let [first, last] = [0, source.width - 1];
    while (first < last && !opaque(first)) first++;
    while (last > first && !opaque(last)) last--;
    texture.add(TILE_FRAME, 0, first, 0, last - first + 1, source.height);
    return { frame: TILE_FRAME, x: first, width: last - first + 1 };
  }

  /** The mean colour of the solid part of a picture's lower third, to carry the ground on below
   * it: a ground strip fades out at its bottom edge. */
  bottomColour(key: string): number {
    const source = this.source(key);
    const top = Math.floor((source.height * 2) / 3);
    const rows = source.height - top;
    const [, context] = canvasOf(source.width, rows);
    context.drawImage(source, 0, top, source.width, rows, 0, 0, source.width, rows);
    const { data } = context.getImageData(0, 0, source.width, rows);
    const sum = [0, 0, 0];
    let n = 0;
    for (let i = 0; i < data.length; i += 4) {
      if (data[i + 3] < 200) continue;
      for (let c = 0; c < 3; c++) sum[c] += data[i + c];
      n++;
    }
    const mean = (c: number) => (n ? Math.round(sum[c] / n) : 0);
    return (mean(0) << 16) | (mean(1) << 8) | mean(2);
  }

  /** A soft round light, white in the middle, for lamps. */
  lamp(): string {
    const key = `${PREFIX}lamp-light`;
    if (this.scene.textures.exists(key)) return key;
    const size = 256;
    const [canvas, context] = canvasOf(size, size);
    const gradient = context.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2);
    gradient.addColorStop(0, 'rgba(255, 222, 160, 1)');
    gradient.addColorStop(0.35, 'rgba(255, 196, 120, 0.45)');
    gradient.addColorStop(1, 'rgba(255, 180, 100, 0)');
    context.fillStyle = gradient;
    context.fillRect(0, 0, size, size);
    this.add(key, canvas);
    return key;
  }

  /** A soft dark ellipse for where someone stands. */
  contact(): string {
    const key = `${PREFIX}contact-shadow`;
    if (this.scene.textures.exists(key)) return key;
    const [canvas, context] = canvasOf(128, 32);
    const gradient = context.createRadialGradient(64, 16, 0, 64, 16, 64);
    gradient.addColorStop(0, 'rgba(30, 20, 12, 0.55)');
    gradient.addColorStop(1, 'rgba(30, 20, 12, 0)');
    context.setTransform(1, 0, 0, 0.25, 0, 12);
    context.fillStyle = gradient;
    context.fillRect(0, 0, 128, 128);
    this.add(key, canvas);
    return key;
  }

  /** Frees every picture this loaded or made. */
  destroy(): void {
    for (const derived of this.derived.values()) this.scene.textures.remove(derived.key);
    for (const texture of this.loading.keys()) if (this.scene.textures.exists(texture)) this.scene.textures.remove(texture);
    this.derived.clear();
    this.loading.clear();
  }

  /** Frees a picture and everything made from it. */
  unload(key: string): void {
    const texture = PREFIX + key;
    for (const [name, derived] of this.derived) {
      if (name.startsWith(`${key}#`) || name.startsWith(`${key}@`)) {
        this.scene.textures.remove(derived.key);
        this.derived.delete(name);
      }
    }
    if (this.scene.textures.exists(texture)) this.scene.textures.remove(texture);
    this.loading.delete(texture);
  }

  private source(key: string): HTMLImageElement | HTMLCanvasElement {
    return this.scene.textures.get(PREFIX + key).getSourceImage() as HTMLImageElement;
  }

  private make(
    name: string,
    key: string,
    draw: (source: HTMLImageElement | HTMLCanvasElement, context: CanvasRenderingContext2D, pad: number) => void,
    scale: number,
    pad: number,
    width?: number,
  ): Derived {
    const known = this.derived.get(name);
    if (known) return known;
    const source = this.source(key);
    const [canvas, context] = canvasOf(
      (width ?? source.width * scale) + 2 * pad,
      source.height * scale + 2 * pad,
    );
    draw(source, context, pad);
    const derived = { key: PREFIX + name, name, scale, pad };
    this.add(derived.key, canvas);
    this.derived.set(name, derived);
    return derived;
  }

  private add(key: string, source: HTMLImageElement | HTMLCanvasElement): void {
    const texture =
      source instanceof HTMLCanvasElement
        ? this.scene.textures.addCanvas(key, source)
        : this.scene.textures.addImage(key, source);
    texture?.setFilter(Phaser.Textures.FilterMode.LINEAR);
  }
}
