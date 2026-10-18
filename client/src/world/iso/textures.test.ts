import { describe, expect, it } from 'vitest';
import { UPLOAD_MS_PER_FRAME, Uploads } from './crossfade';
import { sceneryImages, type SceneryManifest } from './manifest';
import { DECODES_AT_ONCE, Limit, uploadImages, type TextureImage } from './textures';

const manifests = import.meta.glob<SceneryManifest>('../../../../content/art/iso/{scenery,interiors}/*.json', {
  eager: true,
  import: 'default',
});

const tick = () => new Promise((resolve) => setTimeout(resolve, 0));

class FakeBitmap {
  closed = false;
  readonly url: string;
  private readonly stage: FakeStage;

  constructor(url: string, stage: FakeStage) {
    this.url = url;
    this.stage = stage;
  }

  close(): void {
    if (!this.closed) this.stage.open--;
    this.closed = true;
  }
}

class FakeStage {
  readonly decoded: FakeBitmap[] = [];
  readonly textures = new Map<string, FakeBitmap>();
  readonly removed: string[] = [];
  readonly openWhenAdded: boolean[] = [];
  open = 0;
  mostOpen = 0;
  decoding = 0;
  mostDecoding = 0;
  keepsBitmaps = false;
  private readonly failing: Set<string>;

  constructor(failing: string[] = []) {
    this.failing = new Set(failing);
  }

  async decode(url: string): Promise<FakeBitmap> {
    this.decoding++;
    this.mostDecoding = Math.max(this.mostDecoding, this.decoding);
    await tick();
    this.decoding--;
    if (this.failing.has(url)) throw new Error(`${url}: 404`);
    const bitmap = new FakeBitmap(url, this);
    this.decoded.push(bitmap);
    this.open++;
    this.mostOpen = Math.max(this.mostOpen, this.open);
    return bitmap;
  }

  add(key: string, bitmap: FakeBitmap): void {
    this.openWhenAdded.push(!bitmap.closed);
    this.textures.set(key, bitmap);
  }

  remove(key: string): void {
    this.removed.push(key);
    this.textures.delete(key);
  }
}

/** Runs the uploads a frame at a time until `done` settles. */
async function frames(uploads: Uploads, done: Promise<unknown>): Promise<void> {
  let settled = false;
  done.then(
    () => (settled = true),
    () => (settled = true),
  );
  for (let frame = 0; !settled && frame < 10_000; frame++) {
    uploads.run(UPLOAD_MS_PER_FRAME, () => 0);
    await tick();
  }
}

const imagesOf = (manifest: SceneryManifest): TextureImage[] =>
  sceneryImages(manifest).map((image) => ({ key: `iso/${image}`, url: `/${image}` }));

describe('Limit', () => {
  it('runs no more than its size at once, the rest in the order they came', async () => {
    const limit = new Limit(2);
    const started: number[] = [];
    const finish: (() => void)[] = [];
    const runs = [0, 1, 2, 3].map((n) =>
      limit.run(() => {
        started.push(n);
        return new Promise<number>((resolve) => finish.push(() => resolve(n)));
      }),
    );
    await tick();
    expect(started).toEqual([0, 1]);
    finish[1]();
    await tick();
    expect(started).toEqual([0, 1, 2]);
    finish[0]();
    finish[2]();
    await tick();
    finish[3]();
    await expect(Promise.all(runs)).resolves.toEqual([0, 1, 2, 3]);
  });

  it('frees a place when a task fails', async () => {
    const limit = new Limit(1);
    const failed = limit.run(() => Promise.reject(new Error('404')));
    const next = limit.run(() => Promise.resolve('next'));
    await expect(failed).rejects.toThrow('404');
    await expect(next).resolves.toBe('next');
  });
});

describe('uploadImages', () => {
  it.each(Object.keys(manifests).map((path) => [path.split('/').slice(-2).join('/'), manifests[path]]))(
    "adds each of %s's images as a texture and closes it straight after",
    async (_name, manifest) => {
      const stage = new FakeStage();
      const uploads = new Uploads();
      const images = imagesOf(manifest as SceneryManifest);
      const done = uploadImages(images, stage, uploads, new Limit(DECODES_AT_ONCE));
      await frames(uploads, done);
      await done;
      expect([...stage.textures.keys()].sort()).toEqual(images.map(({ key }) => key).sort());
      expect(stage.openWhenAdded.every(Boolean)).toBe(true);
      expect(stage.decoded.every(({ closed }) => closed)).toBe(true);
      expect(stage.open).toBe(0);
    },
  );

  it(`decodes ${DECODES_AT_ONCE} at a time, and holds no more open than that`, async () => {
    const stage = new FakeStage();
    const uploads = new Uploads();
    const images = Array.from({ length: 40 }, (_, i) => ({ key: `key-${i}`, url: `url-${i}` }));
    const done = uploadImages(images, stage, uploads, new Limit(DECODES_AT_ONCE));
    await frames(uploads, done);
    await done;
    expect(stage.textures.size).toBe(40);
    expect(stage.mostDecoding).toBe(DECODES_AT_ONCE);
    expect(stage.mostOpen).toBeLessThanOrEqual(DECODES_AT_ONCE);
  });

  it('leaves the bitmaps open for a renderer that draws from them', async () => {
    const stage = new FakeStage();
    stage.keepsBitmaps = true;
    const uploads = new Uploads();
    const done = uploadImages([{ key: 'key', url: 'url' }], stage, uploads, new Limit(DECODES_AT_ONCE));
    await frames(uploads, done);
    await done;
    expect(stage.decoded.map(({ closed }) => closed)).toEqual([false]);
  });

  it('after a failure, decodes no more, closes what it decoded and removes the textures it added', async () => {
    const stage = new FakeStage(['url-5']);
    const uploads = new Uploads();
    const images = Array.from({ length: 40 }, (_, i) => ({ key: `key-${i}`, url: `url-${i}` }));
    const done = uploadImages(images, stage, uploads, new Limit(DECODES_AT_ONCE));
    await frames(uploads, done);
    await expect(done).rejects.toThrow('url-5: 404');
    expect(stage.textures.size).toBe(0);
    expect(stage.removed.length).toBeGreaterThan(0);
    expect(stage.decoded.every(({ closed }) => closed)).toBe(true);
    expect(stage.decoded.length).toBeLessThan(5 + DECODES_AT_ONCE);
  });
});
