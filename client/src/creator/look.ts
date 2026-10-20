import { flatDoll, loadDoll } from '../dolls/assets';
import type { DollManifest } from '../dolls/manifest';
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
export type DrawPreview = (request: PreviewRequest) => Promise<DollManifest>;

/** Part 4's flat doll for the look, which the server makes at once. */
export const drawPreview: DrawPreview = ({ appearance, character }) => flatDoll(appearance, character);

export type PreviewStage = { show(doll: DollManifest): Promise<void>; destroy(): void };
export type MakeStage = (parent: HTMLElement) => Promise<PreviewStage>;

const dollStage: MakeStage = async (parent) => new (await import('./doll-stage')).DollStage(parent);

export const paintedUrl = (id: string) => `/api/jobs/files/doll/${id}.json`;

export type LoadDoll = (url: string) => Promise<DollManifest>;

const loadFresh: LoadDoll = (url) => loadDoll(url, (input) => fetch(input, { cache: 'no-cache' }));

/** The look's flat doll as it changes, and the doll job's painted one once there is one. */
export class DollPreview {
  readonly root = h('div', { className: 'creator-doll' });
  private readonly dolls = h('div', { className: 'creator-dolls', hidden: true });
  private readonly note = h('p', { className: 'creator-hint' });
  private readonly status = h('p', { className: 'creator-hint' });
  private readonly bar = h('progress', { max: 1, value: 0, hidden: true });
  private watch: JobWatch | null = null;
  private readonly api: CreatorApi;
  private readonly draw: DrawPreview;
  private readonly delay: number;
  private readonly makeStage: MakeStage;
  private readonly load: LoadDoll;
  private stage?: Promise<PreviewStage>;
  private showing: Promise<void> = Promise.resolve();
  private latest: PreviewRequest | null = null;
  private due: PreviewRequest | null = null;
  private drawn = '';
  private drawing = false;
  private disposed = false;
  private timer: ReturnType<typeof setTimeout> | undefined;

  constructor(
    api: CreatorApi,
    draw: DrawPreview = drawPreview,
    delay = PREVIEW_DELAY_MS,
    makeStage: MakeStage = dollStage,
    load: LoadDoll = loadFresh,
  ) {
    this.api = api;
    this.draw = draw;
    this.delay = delay;
    this.makeStage = makeStage;
    this.load = load;
    this.root.append(this.dolls, this.note, this.bar, this.status);
  }

  preview(appearance: Appearance, character?: string): void {
    this.latest = { character, appearance };
    clearTimeout(this.timer);
    this.timer = setTimeout(() => {
      this.due = this.latest;
      if (!this.drawing) void this.redraw();
    }, this.delay);
  }

  /** Shows the character's painted doll in place of the flat one, if the doll job painted one. */
  async show(id: string): Promise<boolean> {
    const key = JSON.stringify(this.latest);
    const doll = await this.load(paintedUrl(id)).catch(() => null);
    if (!doll) this.say('The doll isn’t painted yet: saving paints it.');
    else if (key === JSON.stringify(this.latest)) await this.display(doll, key).catch(() => {});
    return doll !== null;
  }

  async paint(id: string, appearance: Appearance): Promise<Job | null> {
    this.watch?.stop();
    this.preview(appearance, id);
    const key = JSON.stringify(this.latest);
    try {
      const job = await this.api.submit('doll', { character: id, appearance });
      const done = await this.follow(job);
      const url = done.result?.doll;
      if (done.state === 'succeeded' && typeof url === 'string' && !this.disposed) {
        const doll = await this.load(url);
        const fresh = (src?: string) => src && `${src}?job=${done.id}`;
        const painted = { ...doll, flat: fresh(doll.flat) ?? '', painted: fresh(doll.painted) };
        if (key === JSON.stringify(this.latest)) await this.display(painted, key);
      }
      return done;
    } catch (error) {
      this.say(`Couldn’t paint the doll: ${message(error)}`);
      return null;
    }
  }

  dispose(): void {
    this.disposed = true;
    this.watch?.stop();
    clearTimeout(this.timer);
    void this.stage?.then((stage) => stage.destroy());
  }

  private async redraw(): Promise<void> {
    this.drawing = true;
    while (this.due && !this.disposed) {
      const request = this.due;
      this.due = null;
      const key = JSON.stringify(request);
      if (key === this.drawn) continue;
      try {
        const doll = await this.draw(request);
        if (this.disposed) break;
        if (key !== this.drawn) await this.display(doll, key);
      } catch (error) {
        this.note.textContent = `Couldn’t draw the preview: ${message(error)}`;
      }
    }
    this.drawing = false;
  }

  private display(doll: DollManifest, key: string): Promise<void> {
    this.drawn = key;
    this.stage ??= this.makeStage(this.dolls);
    const stage = this.stage;
    const shown = this.showing.then(async () => {
      await (await stage).show(doll);
      this.note.textContent = '';
      this.dolls.hidden = false;
    });
    this.showing = shown.catch(() => {
      if (this.drawn === key) this.drawn = '';
    });
    return shown;
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
      this.say(`Doll: ${describe(current)}`);
    };
    update(job);
    watch.onChange = update;
    const done = await watch.done;
    this.bar.hidden = true;
    if (done.state === 'succeeded') this.say('Doll painted.');
    return done;
  }

  private say(text: string): void {
    this.status.textContent = text;
  }
}
