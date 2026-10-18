import type { Atlas, CreatorApi } from './api';
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

const DIRECTIONS = [
  'down',
  'down_right',
  'right',
  'up_right',
  'up',
  'up_left',
  'left',
  'down_left',
];
const SCALE = 4;

export class SpritePreview {
  readonly root = h('div', { className: 'creator-sprite' });
  private readonly canvas = h('canvas', { width: 1, height: 1 });
  private readonly status = h('p', { className: 'creator-hint' });
  private readonly bar = h('progress', { max: 1, value: 0, hidden: true });
  private watch: JobWatch | null = null;
  private readonly api: CreatorApi;

  constructor(api: CreatorApi) {
    this.api = api;
    this.root.append(this.canvas, this.bar, this.status);
    this.canvas.hidden = true;
  }

  async show(id: string): Promise<boolean> {
    const base = `/api/jobs/files/sprite/${id}`;
    const atlas = await this.api.atlas(`${base}.json`).catch(() => null);
    if (!atlas) {
      this.say('Not drawn yet: saving draws it.');
      return false;
    }
    await this.draw(`${base}.png?v=${Date.now()}`, atlas);
    this.say('');
    return true;
  }

  async render(id: string, appearance: Appearance): Promise<Job | null> {
    this.watch?.stop();
    try {
      const job = await this.api.submit('sprite', { character: id, appearance });
      return await this.follow(job);
    } catch (error) {
      this.say(`Couldn’t draw the sprite: ${message(error)}`);
      return null;
    }
  }

  dispose(): void {
    this.watch?.stop();
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
    const result = done.result as { image?: string; atlas?: string } | null;
    if (done.state === 'succeeded' && result?.image && result.atlas) {
      const atlas = await this.api.atlas(result.atlas);
      if (atlas) await this.draw(`${result.image}?v=${done.id}`, atlas);
      this.say('Sprite drawn.');
    }
    return done;
  }

  private async draw(src: string, atlas: Atlas): Promise<void> {
    const image = new Image();
    image.src = src;
    try {
      await image.decode();
    } catch {
      this.say('Couldn’t load the sprite.');
      return;
    }
    const frames = DIRECTIONS.map((d) => atlas.frames[`${d}-0`]?.frame).filter(
      (f) => f !== undefined,
    );
    if (!frames.length) return;
    const { w, h: height } = frames[0];
    this.canvas.width = frames.length * (w + 2) * SCALE;
    this.canvas.height = height * SCALE;
    const context = this.canvas.getContext('2d');
    if (!context) return;
    context.imageSmoothingEnabled = false;
    frames.forEach((f, i) =>
      context.drawImage(
        image,
        f.x,
        f.y,
        f.w,
        f.h,
        i * (w + 2) * SCALE,
        0,
        f.w * SCALE,
        f.h * SCALE,
      ),
    );
    this.canvas.hidden = false;
  }

  private say(text: string): void {
    this.status.textContent = text;
  }
}
