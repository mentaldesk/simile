// What a SpriteFigure uses of Phaser, for tests in Node: vi.mock('phaser', () => import('./phaser.fixture')).
import type Phaser from 'phaser';

export class FakeImage {
  key: string;
  frame?: string;
  flipX = false;
  tint = -1;

  constructor(_scene: unknown, _x: number, _y: number, key: string, frame?: string) {
    this.key = key;
    this.frame = frame;
  }

  setTexture(key: string, frame?: string): this {
    this.key = key;
    this.frame = frame;
    return this;
  }

  setFlipX(flip: boolean): this {
    this.flipX = flip;
    return this;
  }

  setTint(tint: number): this {
    this.tint = tint;
    return this;
  }

  setOrigin(): this {
    return this;
  }

  setPosition(): this {
    return this;
  }

  setAngle(): this {
    return this;
  }

  setScale(): this {
    return this;
  }
}

class FakeContainer {
  scene?: unknown;
  readonly list: FakeImage[] = [];
  scale = 1;
  private readonly destroyed: (() => void)[] = [];

  constructor(scene: unknown) {
    this.scene = scene;
  }

  add(child: FakeImage): this {
    this.list.push(child);
    return this;
  }

  setScale(scale: number): this {
    this.scale = scale;
    return this;
  }

  setPosition(): this {
    return this;
  }

  once(_event: string, listener: () => void): this {
    this.destroyed.push(listener);
    return this;
  }

  destroy(): void {
    this.destroyed.forEach((listener) => listener());
    this.scene = undefined;
  }
}

export default {
  GameObjects: { Container: FakeContainer, Image: FakeImage, Events: { DESTROY: 'destroy' } },
  Textures: { FilterMode: { LINEAR: 0 } },
};

/** A scene whose textures are the atlases `loaded` and any added since. */
export function fakeScene(loaded: string[] = []): Phaser.Scene {
  const keys = new Set(loaded);
  const textures = {
    exists: (key: string) => keys.has(key),
    addImage: (key: string) => (keys.add(key), { setFilter: () => undefined, add: () => undefined }),
  };
  return { textures } as unknown as Phaser.Scene;
}

/** The image a figure draws. */
export const drawnImage = (figure: object): FakeImage => (figure as { list: FakeImage[] }).list[0];

/** Browser images whose loads the test finishes, in any order, by calling `onload`. */
export function loadingImages(): { onload: () => void }[] {
  const started: { onload: () => void }[] = [];
  class LoadingImage {
    onload = () => undefined;
    onerror = () => undefined;
    set src(_url: string) {
      started.push(this);
    }
  }
  globalThis.Image = LoadingImage as unknown as typeof Image;
  return started;
}
