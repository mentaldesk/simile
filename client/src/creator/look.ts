import { PIXEL_SCALE } from '../world/iso/sheets';
import { WALK_FPS } from '../world/tuning';
import type { CreatorApi } from './api';
import type { Accessory, Appearance } from './character';
import { button, capitalise, h, message } from './dom';
import { type Job, JobWatch, describe } from './jobs';
import {
  ACCESSORIES,
  BUILDS,
  CLOTH_COLOURS,
  HAIR_STYLES,
  PALETTE,
  SKIN_TONES,
  nearest,
} from './palette';

type Colour = 'skin' | 'hair_colour' | 'top_colour' | 'bottom_colour' | 'shoe_colour';

const COLOURS: [Colour, string, string[]][] = [
  ['skin', 'Skin', SKIN_TONES],
  ['hair_colour', 'Hair', CLOTH_COLOURS],
  ['top_colour', 'Top', CLOTH_COLOURS],
  ['bottom_colour', 'Bottoms', CLOTH_COLOURS],
  ['shoe_colour', 'Shoes', CLOTH_COLOURS],
];

export function lookEditor(
  appearance: Appearance,
  onChange: (appearance: Appearance) => void,
  disabled = false,
): HTMLElement {
  const look = structuredClone(appearance);
  const change = () => onChange(structuredClone(look));
  const root = h('div', { className: 'creator-look' });

  const swatches = (field: Colour, choices: string[]) => {
    const row = h('div', { className: 'creator-swatches', role: 'radiogroup' });
    const draw = () => {
      const chosen = nearest(look[field], choices);
      row.replaceChildren(
        ...choices.map((name) =>
          h('button', {
            type: 'button',
            className: 'creator-swatch',
            title: name,
            disabled,
            role: 'radio',
            'aria-label': name,
            'aria-checked': String(name === chosen),
            style: `--swatch: ${PALETTE[name]}`,
            onclick: () => {
              look[field] = PALETTE[name];
              draw();
              change();
            },
          }),
        ),
      );
    };
    draw();
    return row;
  };

  const choice = <T extends string>(
    options: readonly T[],
    current: () => T,
    set: (value: T) => void,
  ) => {
    const row = h('div', { className: 'creator-choices' });
    const draw = () =>
      row.replaceChildren(
        ...options.map((option) =>
          button(
            capitalise(option),
            () => {
              set(option);
              draw();
              change();
            },
            { disabled, 'aria-pressed': String(option === current()) },
          ),
        ),
      );
    draw();
    return row;
  };

  const toggles = () => {
    const row = h('div', { className: 'creator-choices' });
    const draw = () =>
      row.replaceChildren(
        ...ACCESSORIES.map((item: Accessory) =>
          button(
            capitalise(item),
            () => {
              look.accessories = look.accessories.includes(item)
                ? look.accessories.filter((a) => a !== item)
                : [...look.accessories, item];
              draw();
              change();
            },
            { disabled, 'aria-pressed': String(look.accessories.includes(item)) },
          ),
        ),
      );
    draw();
    return row;
  };

  for (const [field, label, choices] of COLOURS) {
    root.append(
      h('div', { className: 'creator-row' }, h('span', {}, label), swatches(field, choices)),
    );
  }
  root.append(
    h(
      'div',
      { className: 'creator-row' },
      h('span', {}, 'Hair style'),
      choice(
        HAIR_STYLES,
        () => look.hair_style,
        (v) => (look.hair_style = v),
      ),
    ),
    h(
      'div',
      { className: 'creator-row' },
      h('span', {}, 'Build'),
      choice(
        BUILDS,
        () => look.build,
        (v) => (look.build = v),
      ),
    ),
    h('div', { className: 'creator-row' }, h('span', {}, 'Extras'), toggles()),
  );
  return root;
}

export const PREVIEW_DELAY_MS = 150;

export type PreviewRequest = { character?: string; appearance: Appearance };
export type DrawPreview = (request: PreviewRequest) => Promise<Blob>;

export async function drawPreview(request: PreviewRequest): Promise<Blob> {
  const response = await fetch('/api/art/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(request),
  });
  if (!response.ok) {
    const data = await response.json().catch(() => null);
    throw new Error(data?.error ?? `the server answered ${response.status}`);
  }
  return response.blob();
}

const FRAME = { width: 16, height: 24 };
const WALK = [0, 1, 2, 1];
const GAP = 4;

export class SpritePreview {
  readonly root = h('div', { className: 'creator-sprite' });
  private readonly canvas = h('canvas', { width: 1, height: 1, hidden: true });
  private readonly note = h('p', { className: 'creator-hint' });
  private readonly status = h('p', { className: 'creator-hint' });
  private readonly bar = h('progress', { max: 1, value: 0, hidden: true });
  private watch: JobWatch | null = null;
  private readonly api: CreatorApi;
  private readonly draw: DrawPreview;
  private readonly delay: number;
  private latest: PreviewRequest | null = null;
  private due: PreviewRequest | null = null;
  private drawn = '';
  private drawing = false;
  private disposed = false;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private walk: ReturnType<typeof setInterval> | undefined;
  private frames: ImageBitmap | null = null;
  private step = 0;

  constructor(api: CreatorApi, draw: DrawPreview = drawPreview, delay = PREVIEW_DELAY_MS) {
    this.api = api;
    this.draw = draw;
    this.delay = delay;
    this.root.append(this.canvas, this.note, this.bar, this.status);
  }

  preview(appearance: Appearance, character?: string): void {
    this.latest = { character, appearance };
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.due = this.latest;
      if (!this.drawing) void this.redraw();
    }, this.delay);
  }

  async show(id: string): Promise<boolean> {
    const atlas = await this.api.atlas(`/api/jobs/files/sprite/${id}.json`).catch(() => null);
    if (!atlas) this.say('The sprite isn’t saved yet: saving draws it.');
    return atlas !== null;
  }

  async render(id: string, appearance: Appearance): Promise<Job | null> {
    this.watch?.stop();
    this.preview(appearance, id);
    try {
      const job = await this.api.submit('sprite', { character: id, appearance });
      return await this.follow(job);
    } catch (error) {
      this.say(`Couldn’t draw the sprite: ${message(error)}`);
      return null;
    }
  }

  dispose(): void {
    this.disposed = true;
    this.watch?.stop();
    clearTimeout(this.timer);
    clearInterval(this.walk);
  }

  private async redraw(): Promise<void> {
    this.drawing = true;
    while (this.due && !this.disposed) {
      const request = this.due;
      this.due = null;
      const key = JSON.stringify(request);
      if (key === this.drawn) continue;
      try {
        const frames = await createImageBitmap(await this.draw(request));
        if (this.disposed) break;
        this.frames = frames;
        this.drawn = key;
        this.note.textContent = '';
        this.paint();
        this.walk ??= setInterval(() => {
          this.step = (this.step + 1) % WALK.length;
          this.paint();
        }, 1000 / WALK_FPS);
      } catch (error) {
        this.note.textContent = `Couldn’t draw the preview: ${message(error)}`;
      }
    }
    this.drawing = false;
  }

  private paint(): void {
    const frames = this.frames;
    if (!frames) return;
    const { width, height } = FRAME;
    const directions = Math.floor(frames.height / height);
    this.canvas.width = (directions * (width + GAP) - GAP) * PIXEL_SCALE;
    this.canvas.height = height * PIXEL_SCALE;
    const context = this.canvas.getContext('2d');
    if (!context) return;
    context.imageSmoothingEnabled = false;
    context.scale(PIXEL_SCALE, PIXEL_SCALE);
    const x = WALK[this.step] * width;
    for (let row = 0; row < directions; row++) {
      const [y, left] = [row * height, row * (width + GAP)];
      context.drawImage(frames, x, y, width, height, left, 0, width, height);
    }
    this.canvas.hidden = false;
  }

  private async follow(job: Job): Promise<Job> {
    const watch = new JobWatch(job, {
      connect: (id) => this.api.watch(id),
      poll: (id) => this.api.job(id),
    });
    this.watch = watch;
    const update = (current: Job) => {
      this.bar.hidden = false;
      this.bar.value = current.progress;
      this.say(`Sprite: ${describe(current)}`);
    };
    update(job);
    watch.onChange = update;
    const done = await watch.done;
    this.bar.hidden = true;
    if (done.state === 'succeeded') this.say('Sprite saved.');
    return done;
  }

  private say(text: string): void {
    this.status.textContent = text;
  }
}
