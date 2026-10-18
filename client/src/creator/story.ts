import type { Suggestion } from './api';
import type { Character, Craft, Gender, HookKind, HookSide, Medium } from './character';
import { button, h, humanise, labelled, select, textArea, textInput } from './dom';
import { type Draft, MAX_MANNERISMS, type Work } from './draft';

type Edit = (patch: Work) => void;

const GENDERS = [
  ['', '—'],
  ['woman', 'Woman'],
  ['man', 'Man'],
  ['nonbinary', 'Nonbinary'],
] as const;

const MEDIA: readonly (readonly [Medium | 'drawn' | '', string])[] = [
  ['', 'Nothing'],
  ['writing', 'Writing'],
  ['mural', 'A mural'],
  ['painting', 'Painting'],
];

const TIES: Partial<Record<`${HookKind}:${HookSide}`, string>> = {
  'estranged_sibling:mutual': 'A brother or sister they no longer speak to',
  'ex_partner:mutual': 'An ex-partner',
  'old_friend:mutual': 'An old friend from before',
  'rival:mutual': 'A rival',
  'debt:actor': 'Someone they borrowed money from and still owe',
  'debt:target': 'Someone who borrowed money from them and still owes it',
  'secret:actor': 'Someone who saw them do something they want kept hidden',
  'secret:target': 'Someone they saw do something that person wants kept hidden',
  'betrayal:actor': 'Someone they betrayed',
  'betrayal:target': 'Someone who betrayed them',
  'saved_life:actor': 'Someone whose life they saved',
  'saved_life:target': 'Someone who saved their life',
};

export function age(work: Work, year = new Date().getUTCFullYear()): number | null {
  return work.birth_year === undefined || Number.isNaN(work.birth_year)
    ? null
    : year - work.birth_year;
}

export function backgroundView(draft: Draft, edit: Edit, disabled: boolean): HTMLElement {
  const w = draft.work;
  const drawn = draft.written ? undefined : 'Drawn when it’s written';
  const ageHint = h('small', {});
  const showAge = () => {
    const years = age(draft.work);
    ageHint.textContent = years === null ? '' : `${years} now`;
  };
  showAge();
  const arrival = h('div', { className: 'creator-arrival' });
  const drawArrival = () => {
    const current = draft.work.arrival;
    const how = current === undefined ? '' : current === null ? 'born' : 'came';
    const options = [
      ['', drawn ? 'Drawn when it’s written' : '—'],
      ['born', 'Born in the village'],
      ['came', 'Came here'],
    ] as const;
    arrival.replaceChildren(
      select(
        how,
        options,
        (value) => {
          edit({
            arrival:
              value === 'born'
                ? null
                : value === 'came'
                  ? { age: Math.min(30, age(draft.work) ?? 30), reason: '' }
                  : undefined,
          });
          drawArrival();
        },
        { disabled, 'aria-label': 'Born here or came here' },
      ),
    );
    if (current) {
      arrival.append(
        labelled(
          'At',
          h('input', {
            type: 'number',
            min: 0,
            max: 120,
            value: current.age,
            disabled,
            oninput: (event) =>
              edit({
                arrival: { ...current, age: Number((event.target as HTMLInputElement).value) },
              }),
          }),
        ),
        labelled(
          'Why',
          textInput(
            current.reason,
            (reason) => {
              current.reason = reason;
              edit({ arrival: { ...current } });
            },
            { placeholder: 'for a job', disabled },
          ),
        ),
      );
    }
  };
  drawArrival();
  return h(
    'div',
    { className: 'creator-grid' },
    labelled(
      'Name',
      textInput(w.name ?? '', (name) => edit({ name }), { placeholder: drawn, disabled }),
    ),
    labelled(
      'Born in',
      h('input', {
        type: 'number',
        min: 1900,
        max: 2026,
        value: w.birth_year ?? '',
        placeholder: drawn,
        disabled,
        oninput: (event) => {
          const text = (event.target as HTMLInputElement).value;
          edit({ birth_year: text ? Number(text) : undefined });
          showAge();
        },
      }),
      ageHint,
    ),
    labelled(
      'Gender',
      select(
        w.gender ?? '',
        GENDERS,
        (gender) => edit({ gender: (gender || undefined) as Gender | undefined }),
        { disabled },
      ),
    ),
    labelled(
      'From',
      textInput(w.origin ?? '', (origin) => edit({ origin }), {
        placeholder: drawn ?? 'A country',
        disabled,
      }),
      'Where they were born, or where their family is from.',
    ),
    labelled(
      'Occupation',
      textInput(w.occupation ?? '', (occupation) => edit({ occupation }), {
        placeholder: drawn,
        disabled,
      }),
    ),
    h('div', { className: 'creator-field' }, h('span', {}, 'Arrival'), arrival),
    h(
      'p',
      { className: 'creator-hint creator-wide' },
      'Their wound, secret and want are drawn again with each biography, and show in what it says.',
    ),
  );
}

export function biographyView(
  draft: Draft,
  edit: Edit,
  disabled: boolean,
  onSuggestion: (suggestion: Suggestion, accepted: boolean) => void,
): HTMLElement {
  const w = draft.work;
  const root = h('div', { className: 'creator-biography' });
  if (draft.suggestions.length || draft.notes.length)
    root.append(suggestionsView(draft, onSuggestion, disabled));
  if (!draft.written)
    root.append(
      h(
        'p',
        { className: 'creator-hint' },
        'Claude writes all of this, streamed as it goes. Anything you write here first is kept.',
      ),
    );

  const past = w.past ?? [];
  if (past.length) {
    root.append(
      h('h4', {}, 'Life events'),
      h(
        'ol',
        { className: 'creator-events' },
        past.map((memory, i) =>
          h(
            'li',
            {},
            h('span', { className: 'creator-at' }, `At ${memory.age}`),
            textArea(
              memory.content,
              (content) => {
                const next = [...(draft.work.past ?? [])];
                next[i] = { ...next[i], content };
                edit({ past: next });
              },
              { rows: 2, disabled, 'aria-label': `Life event ${i + 1}` },
            ),
          ),
        ),
      ),
    );
  }

  const prose = (
    field: 'backstory' | 'persona' | 'speaking_style',
    label: string,
    rows: number,
    hint?: string,
  ) =>
    labelled(
      label,
      textArea(w[field] ?? '', (text) => edit({ [field]: text }), { rows, disabled }),
      hint,
    );
  const craftForm = textInput(
    w.craft?.form ?? '',
    (form) => edit({ craft: { ...(draft.work.craft as Craft), form } }),
    {
      placeholder: 'plain verse about the river',
      disabled: disabled || !w.craft,
      'aria-label': 'What they make',
    },
  );
  root.append(
    h(
      'div',
      { className: 'creator-grid' },
      h(
        'div',
        { className: 'creator-wide' },
        prose(
          'backstory',
          'Backstory',
          8,
          'Their whole life, for the debug view and for assets. Other residents never see it.',
        ),
      ),
      prose('persona', 'How they come across', 4),
      prose('speaking_style', 'How they speak', 4),
      labelled(
        'Verbal habits',
        textArea(
          (w.mannerisms ?? []).join('\n'),
          (text) => {
            const mannerisms = lines(text);
            edit({ mannerisms: mannerisms.length ? mannerisms : undefined });
          },
          { rows: 3, disabled },
        ),
        `Up to ${MAX_MANNERISMS}, one a line, such as “answers a question with another question”. ` +
          'They show now and then in conversation. A biography reroll draws new ones.',
      ),
      labelled(
        'Interests',
        textArea(
          (w.interests ?? []).join('\n'),
          (text) => edit({ interests: lines(text) }),
          { rows: 4, disabled },
        ),
        'One a line, specific.',
      ),
      h(
        'div',
        { className: 'creator-field' },
        h('span', {}, 'What they make'),
        select(
          w.craft === undefined && !draft.written ? 'drawn' : (w.craft?.medium ?? ''),
          draft.written ? MEDIA : [['drawn', 'Drawn when it’s written'], ...MEDIA],
          (medium) => {
            const form = draft.work.craft?.form ?? '';
            if (medium === 'drawn') edit({ craft: undefined });
            else edit({ craft: medium ? { medium, form } : null });
            craftForm.disabled = disabled || !medium || medium === 'drawn';
          },
          { disabled, 'aria-label': 'Medium' },
        ),
        craftForm,
      ),
    ),
  );

  const hooks = w.hooks ?? [];
  if (hooks.length) {
    root.append(
      h('h4', {}, 'Ties'),
      h(
        'p',
        { className: 'creator-hint' },
        'Casting binds each to someone in the village, so they never name the other person.',
      ),
      h(
        'ol',
        { className: 'creator-events' },
        hooks.map((hook, i) =>
          h(
            'li',
            {},
            h(
              'span',
              { className: 'creator-at' },
              TIES[`${hook.kind}:${hook.side}`] ?? humanise(hook.kind),
            ),
            textArea(
              hook.description,
              (description) => {
                const next = [...(draft.work.hooks ?? [])];
                next[i] = { ...next[i], description };
                edit({ hooks: next });
              },
              { rows: 2, disabled, 'aria-label': `Tie ${i + 1}` },
            ),
          ),
        ),
      ),
    );
  }
  return root;
}

function lines(text: string): string[] {
  return text
    .split('\n')
    .map((s) => s.trim())
    .filter(Boolean);
}

function suggestionsView(
  draft: Draft,
  onSuggestion: (suggestion: Suggestion, accepted: boolean) => void,
  disabled: boolean,
): HTMLElement {
  const count = draft.suggestions.length;
  const all = (accepted: boolean) =>
    [...draft.suggestions].forEach((s) => onSuggestion(s, accepted));
  return h(
    'div',
    { className: 'creator-suggestions' },
    count
      ? h(
          'header',
          {},
          h('h4', {}, `The critic suggests ${count} ${count === 1 ? 'change' : 'changes'}`),
          count > 1
            ? h(
                'div',
                { className: 'creator-actions' },
                button('Accept all', () => all(true), { disabled }),
                button('Ignore all', () => all(false), { disabled }),
              )
            : '',
        )
      : '',
    draft.suggestions.map((s) =>
      h(
        'div',
        { className: 'creator-suggestion' },
        h('b', {}, fieldName(s.field, draft.work)),
        h('del', {}, s.current),
        h('ins', {}, s.suggested),
        h(
          'div',
          { className: 'creator-actions' },
          button('Accept', () => onSuggestion(s, true), { disabled }),
          button('Ignore', () => onSuggestion(s, false), { disabled }),
        ),
      ),
    ),
    draft.notes.length
      ? h(
          'details',
          {},
          h('summary', {}, 'The critic’s notes'),
          h(
            'ul',
            {},
            draft.notes.map((note) => h('li', {}, note)),
          ),
        )
      : '',
  );
}

function fieldName(field: string, work: Partial<Character>): string {
  const match = /^(\w+)\[(\d+)\]$/.exec(field);
  if (!match)
    return (
      { speaking_style: 'How they speak', persona: 'How they come across' }[field] ??
      humanise(field)
    );
  const index = Number(match[2]);
  if (match[1] === 'past')
    return `Life event ${index + 1}${work.past?.[index] ? `, at ${work.past[index].age}` : ''}`;
  return `Tie ${index + 1}`;
}
