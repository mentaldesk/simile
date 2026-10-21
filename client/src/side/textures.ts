import Phaser from 'phaser';
import { stretchParts } from './layout';

const PREFIX = 'side:';
const SHADOW = '#1e140c';
const TILE_FRAME = 'tile';
/** Alpha above which a column of a tiling picture counts as drawn. */
const OPAQUE = 8;

/** `name` makes more from it; `scale` and `pad` scale it back up. */
export type Derived = { key: string; name: string; scale: number; pad: number };

function canvasOf(width: number, height: number): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const canvas = document.createElement('canvas');
  canvas.width = Math.max(1, Math.ceil(width));
  canvas.height = Math.max(1, Math.ceil(height));
  const context = canvas.getContext('2d')!;
  context.imageSmoothingQuality = 'high';
  return [canvas, context];
}

/** A card with a darker edge and a lighter top, from (edge, edge) to (width - edge, height - edge). */
function card(context: CanvasRenderingContext2D, edge: number, width: number, height: number, fill: string, line: string): void {
  context.beginPath();
  context.roundRect(edge, edge, width - 2 * edge, height - 2 * edge, 10);
  context.fillStyle = fill;
  context.fill();
  const shine = context.createLinearGradient(0, edge, 0, height - edge);
  shine.addColorStop(0, 'rgba(255, 255, 255, 0.18)');
  shine.addColorStop(1, 'rgba(0, 0, 0, 0.12)');
  context.fillStyle = shine;
  context.fill();
  context.lineWidth = edge;
  context.strokeStyle = line;
  context.stroke();
}

function lettering(context: CanvasRenderingContext2D, text: string, x: number, y: number, font: string, fill: string): void {
  context.font = font;
  context.textAlign = 'center';
  context.textBaseline = 'middle';
  context.fillStyle = 'rgba(0, 0, 0, 0.25)';
  context.fillText(text, x + 1.5, y + 2);
  context.fillStyle = fill;
  context.fillText(text, x, y);
}

export class SideTextures {
  private readonly scene: Phaser.Scene;
  private readonly loading = new Map<string, Promise<string>>();
  private readonly derived = new Map<string, Derived>();

  constructor(scene: Phaser.Scene) {
    this.scene = scene;
  }

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

  /** Blurred and dark, from its alpha. */
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

  light(key: string, scale: number, blur = 0): Derived {
    return this.make(`${key}#light${scale}x${blur}`, key, (source, context, pad) => {
      context.fillStyle = '#000';
      context.fillRect(0, 0, context.canvas.width, context.canvas.height);
      if (blur) context.filter = `blur(${blur}px)`;
      context.drawImage(source, pad, pad, source.width * scale, source.height * scale);
    }, scale, Math.ceil(blur * 2.5));
  }

  blurred(key: string, blur: number): Derived {
    return this.make(`${key}#blur${blur}`, key, (source, context, pad) => {
      context.filter = `blur(${blur}px)`;
      context.drawImage(source, pad, pad);
    }, 1, 0);
  }

  /** Its ends kept and its middle repeated. */
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

  band(key: string, width: number, height: number): Derived {
    return this.make(`${key}#band${width}x${height}`, key, (source, context) => {
      const step = (source.width * height) / source.height;
      for (let x = 0; x < width; x += step) context.drawImage(source, x, 0, step, height);
    }, height / this.source(key).height, 0, width);
  }

  /** Darker under the ceiling and in the corners. */
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

  /** Without the empty columns some of #309's strips start with, so copies meet. */
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

  /** A ground strip fades out at its bottom edge. */
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

  /** A lit green EXIT sign, drawn large to be scaled down. */
  exitSign(): string {
    const name = 'exit-sign';
    if (this.scene.textures.exists(PREFIX + name)) return name;
    const [width, height, edge] = [200, 84, 4];
    const [canvas, context] = canvasOf(width, height);
    card(context, edge, width, height, '#2f7a4f', '#173f29');
    context.strokeStyle = 'rgba(246, 240, 216, 0.35)';
    context.lineWidth = 2;
    context.beginPath();
    context.roundRect(edge + 7, edge + 7, width - 2 * edge - 14, height - 2 * edge - 14, 6);
    context.stroke();
    lettering(context, 'EXIT', width / 2, height / 2 + 1, 'bold 48px "Trebuchet MS", "Helvetica Neue", Arial, sans-serif', '#f8f2dc');
    this.add(PREFIX + name, canvas);
    return name;
  }

  /** A fingerpost naming where a way goes, drawn large to be scaled down, its post's foot at the bottom middle. */
  signpost(label: string): string {
    const name = `signpost:${label}`;
    if (this.scene.textures.exists(PREFIX + name)) return name;
    const font = 'bold 46px Georgia, "Times New Roman", serif';
    const [, measure] = canvasOf(1, 1);
    measure.font = font;
    const arrow = 34;
    const board = { width: Math.ceil(measure.measureText(label).width) + arrow + 64, height: 96 };
    const [width, height, post] = [board.width + 8, 600, 30];
    const [canvas, context] = canvasOf(width, height);
    context.fillStyle = '#6e4b30';
    context.fillRect(width / 2 - post / 2, board.height - 10, post, height - board.height + 10);
    context.fillStyle = 'rgba(0, 0, 0, 0.18)';
    context.fillRect(width / 2 + post / 2 - 9, board.height - 10, 9, height - board.height + 10);
    card(context, 4, board.width + 4, board.height, '#f1e4c2', '#5b3f27');
    const left = 4 + 30;
    context.fillStyle = '#7a2e1f';
    context.beginPath();
    context.moveTo(left, board.height / 2 + 14);
    context.lineTo(left + arrow / 2, board.height / 2 - 18);
    context.lineTo(left + arrow, board.height / 2 + 14);
    context.closePath();
    context.fill();
    lettering(context, label, left + arrow + 14 + (board.width - arrow - 64) / 2, board.height / 2 + 2, font, '#3b2a1c');
    this.add(PREFIX + name, canvas);
    return name;
  }

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

  destroy(): void {
    for (const derived of this.derived.values()) this.scene.textures.remove(derived.key);
    for (const texture of this.loading.keys()) if (this.scene.textures.exists(texture)) this.scene.textures.remove(texture);
    this.derived.clear();
    this.loading.clear();
  }

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
    if (source instanceof HTMLCanvasElement) this.scene.textures.addCanvas(key, source);
    else this.scene.textures.addImage(key, source);
  }
}
