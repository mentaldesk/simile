import type { Uploads } from './crossfade';

/** How many images are fetched and decoded at once. Each is held only until its texture is added. */
export const DECODES_AT_ONCE = 6;

/** Runs at most `size` tasks at a time, and the rest in the order they came. */
export class Limit {
  private running = 0;
  private readonly waiting: (() => void)[] = [];
  private readonly size: number;

  constructor(size: number) {
    this.size = size;
  }

  async run<T>(task: () => Promise<T>): Promise<T> {
    if (this.running < this.size) this.running++;
    else await new Promise<void>((resolve) => this.waiting.push(resolve));
    try {
      return await task();
    } finally {
      const next = this.waiting.shift();
      if (next) next();
      else this.running--;
    }
  }
}

export type Bitmap = { close(): void };

/** How textures reach the scene: Phaser in the game, a fake in tests. */
export type TextureStage<B extends Bitmap> = {
  decode(url: string): Promise<B>;
  add(key: string, bitmap: B): void;
  remove(key: string): void;
  /** The canvas renderer draws from the bitmaps, so they stay open. */
  keepsBitmaps?: boolean;
};

export type TextureImage = { key: string; url: string };

/**
 * Decodes each image within `limit` and adds it as a texture in `uploads`, then closes it, since the
 * GPU has its copy. After a failure it decodes no more, removes the textures it added and throws.
 */
export async function uploadImages<B extends Bitmap>(
  images: readonly TextureImage[],
  stage: TextureStage<B>,
  uploads: Uploads,
  limit: Limit,
): Promise<void> {
  const added: string[] = [];
  let failure: { reason: unknown } | undefined;
  const upload = async ({ key, url }: TextureImage) => {
    if (failure) return;
    try {
      const bitmap = await stage.decode(url);
      await uploads.add([
        () => {
          try {
            stage.add(key, bitmap);
            added.push(key);
          } finally {
            if (!stage.keepsBitmaps) bitmap.close();
          }
        },
      ]);
    } catch (reason) {
      failure ??= { reason };
    }
  };
  await Promise.all(images.map((image) => limit.run(() => upload(image))));
  if (!failure) return;
  for (const key of added) stage.remove(key);
  throw failure.reason;
}
