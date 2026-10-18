import type { Traits, Values } from './character';
import { button, h, humanise } from './dom';
import type { Draft } from './draft';
import type { SampleLine } from './sample-line';
import {
  ARCHETYPES,
  CORE_VALUES,
  type CoreValue,
  LATENT_RANGE,
  TRAITS,
  TRAIT_ENDS,
  ranked,
} from './values';

const TRAIT_FIELDS: (keyof Traits)[] = [
  'sociability',
  'negativity_bias',
  'forgiveness',
  'first_impressions',
];

type Options = {
  draft: Draft;
  sample: SampleLine | null;
  disabled: boolean;
  onValues: (values: Values) => void;
  onTraits: (traits: Traits) => void;
};

function slider(
  min: number,
  max: number,
  step: number,
  value: number,
  onInput: (value: number) => void,
  disabled: boolean,
  label: string,
): HTMLInputElement {
  return h('input', {
    type: 'range',
    min,
    max,
    step,
    value,
    disabled,
    'aria-label': label,
    oninput: (event) => onInput(Number((event.target as HTMLInputElement).value)),
  });
}

export function valuesView({ draft, sample, disabled, onValues, onTraits }: Options): HTMLElement {
  const model = draft.values;
  const summary = h('p', { className: 'creator-summary' });
  const latentInputs = new Map<string, HTMLInputElement>();
  const latentReadouts = new Map<string, HTMLElement>();
  const valueInputs = new Map<CoreValue, HTMLInputElement>();
  const valueReadouts = new Map<CoreValue, HTMLElement>();

  const show = (values: Values) => {
    const order = ranked(values);
    const list = (items: [string, number][]) =>
      items.map(([v, s]) => `${humanise(v).toLowerCase()} ${s.toFixed(2)}`).join(', ');
    summary.replaceChildren(
      h('span', {}, h('b', {}, 'Cares most about '), list(order.slice(0, 5))),
      h('span', {}, h('b', {}, 'Least about '), list(order.slice(-5).reverse())),
    );
    for (const v of CORE_VALUES) {
      const input = valueInputs.get(v);
      if (input && document.activeElement !== input) input.value = String(values[v]);
      valueReadouts.get(v)?.replaceChildren((values[v] ?? 0).toFixed(2));
    }
    for (const t of TRAITS) {
      const input = latentInputs.get(t);
      if (input && document.activeElement !== input) input.value = String(model.latent[t]);
      latentReadouts.get(t)?.replaceChildren(signed(model.latent[t]));
    }
  };

  const changed = () => {
    const values = model.values();
    show(values);
    onValues(values);
  };

  const presets = h(
    'div',
    { className: 'creator-choices creator-presets' },
    ARCHETYPES.map((archetype) =>
      button(
        archetype.name,
        () => {
          model.setLatent(archetype.latent);
          changed();
        },
        { title: archetype.blurb, disabled },
      ),
    ),
  );

  const traits = h(
    'div',
    { className: 'creator-traits' },
    TRAITS.map((trait) => {
      const [low, high] = TRAIT_ENDS[trait];
      const readout = h('output', {}, signed(model.latent[trait]));
      latentReadouts.set(trait, readout);
      const input = slider(
        -LATENT_RANGE,
        LATENT_RANGE,
        0.1,
        model.latent[trait],
        (z) => {
          model.setTrait(trait, z);
          changed();
        },
        disabled,
        humanise(trait),
      );
      latentInputs.set(trait, input);
      return h(
        'div',
        { className: 'creator-trait' },
        h('div', { className: 'creator-trait-name' }, h('b', {}, humanise(trait)), readout),
        input,
        h('div', { className: 'creator-ends' }, h('span', {}, low), h('span', {}, high)),
      );
    }),
  );

  const values = draft.work.values ?? {};
  const advanced = h(
    'details',
    { className: 'creator-advanced' },
    h('summary', {}, 'All 24 values, and the traits behind behaviour'),
    h(
      'div',
      { className: 'creator-values' },
      CORE_VALUES.map((v) => {
        const readout = h('output', {}, (values[v] ?? 0).toFixed(2));
        valueReadouts.set(v, readout);
        const input = slider(
          0,
          1,
          0.01,
          values[v] ?? 0.5,
          (score) => {
            model.setValue(v, score);
            changed();
          },
          disabled,
          humanise(v),
        );
        valueInputs.set(v, input);
        return h(
          'label',
          { className: 'creator-value' },
          h('span', {}, humanise(v)),
          input,
          readout,
        );
      }),
    ),
    draft.work.traits ? traitSliders(draft.work.traits, disabled, onTraits) : null,
  );

  const root = h(
    'div',
    { className: 'creator-values-view' },
    presets,
    traits,
    summary,
    sample ? sampleBox(sample, disabled) : sampleUnavailable(),
    advanced,
  );
  show(values);
  return root;
}

function traitSliders(
  traits: Traits,
  disabled: boolean,
  onTraits: (traits: Traits) => void,
): HTMLElement {
  const current = { ...traits };
  return h(
    'div',
    { className: 'creator-values' },
    h(
      'p',
      { className: 'creator-hint creator-wide' },
      'How they behave with others. Rerolling values works these out again.',
    ),
    TRAIT_FIELDS.map((field) => {
      const readout = h('output', {}, current[field].toFixed(2));
      const input = slider(
        0,
        1,
        0.01,
        current[field],
        (score) => {
          current[field] = score;
          readout.textContent = score.toFixed(2);
          onTraits({ ...current });
        },
        disabled,
        humanise(field),
      );
      return h(
        'label',
        { className: 'creator-value' },
        h('span', {}, humanise(field)),
        input,
        readout,
      );
    }),
  );
}

function sampleUnavailable(): HTMLElement {
  return h(
    'div',
    { className: 'creator-sample' },
    h(
      'p',
      { className: 'creator-hint' },
      'Once the character is written, a line in their words shows what these values do.',
    ),
  );
}

function sampleBox(sample: SampleLine, disabled: boolean): HTMLElement {
  const quote = h('blockquote', {});
  const status = h('small', {});
  const ask = button('New line', () => void sample.request(), { disabled });
  const draw = () => {
    quote.textContent = sample.line ? `“${sample.line}”` : '';
    quote.hidden = !sample.line;
    quote.classList.toggle('creator-stale', sample.stale);
    ask.disabled = disabled || sample.state === 'asking';
    status.textContent = sampleStatus(sample);
  };
  sample.onChange = draw;
  draw();
  return h(
    'div',
    { className: 'creator-sample' },
    h('div', { className: 'creator-sample-head' }, h('b', {}, 'In their words'), ask),
    quote,
    status,
  );
}

function sampleStatus(sample: SampleLine): string {
  switch (sample.state) {
    case 'idle':
      return 'Move a slider, or ask for a line. Each line is one Claude call.';
    case 'waiting':
      return 'A new line once the sliders settle…';
    case 'asking':
      return 'Writing a line in their words…';
    case 'failed':
      return `Couldn’t write a line: ${sample.error}`;
    case 'ready':
      if (!sample.stale) return '';
      return sample.autoLeft > 0
        ? 'Values changed.'
        : 'Values changed. Ask for a new line to hear them.';
  }
}

function signed(z: number): string {
  return `${z > 0 ? '+' : ''}${z.toFixed(1)}`;
}
