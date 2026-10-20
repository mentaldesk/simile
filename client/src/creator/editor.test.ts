// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Capabilities, CreatorApi, GenerationEvent } from './api';
import { character } from './character.fixture';
import { Draft } from './draft';
import { Editor, type EditorContext } from './editor';
import type { Job, SocketLike } from './jobs';
import { LibraryView } from './library';

// Its globs of content/ don't load under jsdom.
vi.mock('../dolls/assets', () => ({
  flatDoll: vi.fn(() => new Promise(() => {})),
  loadDoll: vi.fn(async () => Promise.reject(new Error('Not painted'))),
}));

const CAN_PAINT: Capabilities = {
  machine: {},
  kinds: { doll: { available: true, reason: null } },
};

function job(overrides: Partial<Job>): Job {
  return {
    id: '3f9c2a7d1b6e4c08',
    kind: 'doll',
    state: 'queued',
    progress: 0,
    message: null,
    error: null,
    result: null,
    created: '2026-10-18T09:30:00Z',
    started: null,
    finished: null,
    ...overrides,
  };
}

function fakeApi() {
  const socket: SocketLike = { onmessage: null, onclose: null, close: () => {} };
  return {
    characters: vi.fn(async () => [
      character(),
      character({ id: 'olivia', name: 'Olivia', source: 'premade' }),
    ]),
    create: vi.fn(async (c) => c),
    update: vi.fn(async (c) => ({ ...c, version: c.version + 1 })),
    remove: vi.fn(async () => {}),
    exportUrl: (id: string) => `/api/characters/${id}/export`,
    importFile: vi.fn(async () => character({ id: 'wren_abernethy_2' })),
    generate: vi.fn(),
    reroll: vi.fn(),
    player: vi.fn(),
    savePlayer: vi.fn(),
    capabilities: vi.fn(async () => CAN_PAINT),
    submit: vi.fn(async () => job({ state: 'succeeded', progress: 1 })),
    job: vi.fn(),
    cancel: vi.fn(),
    watch: vi.fn(() => socket),
    voices: vi.fn(async () => []),
    record: vi.fn(),
    pick: vi.fn(),
    say: vi.fn(),
  } satisfies CreatorApi;
}

function context(api: CreatorApi, capabilities: Capabilities | null = CAN_PAINT): EditorContext {
  return { api, capabilities, back: vi.fn(), saved: vi.fn(), deleted: vi.fn() };
}

async function* stream(...events: GenerationEvent[]): AsyncGenerator<GenerationEvent> {
  yield* events;
}

const written = (overrides = {}): GenerationEvent => ({
  type: 'done',
  character: character(overrides),
  suggestions: [],
  notes: [],
  warnings: [],
});

function buttonCalled(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll('button')].find((b) => b.textContent === text);
  if (!found) throw new Error(`No ${text} button`);
  return found;
}

function field(root: HTMLElement, label: string): HTMLInputElement {
  const found = [...root.querySelectorAll('label')].find(
    (l) => l.querySelector('span')?.textContent === label,
  );
  const input = found?.querySelector('input, textarea');
  if (!input) throw new Error(`No ${label} field`);
  return input as HTMLInputElement;
}

function type(input: HTMLInputElement, text: string): void {
  input.value = text;
  input.dispatchEvent(new Event('input'));
}

const settle = () => new Promise((resolve) => setTimeout(resolve, 0));

afterEach(() => {
  document.body.replaceChildren();
});

describe('the editor', () => {
  it('writes a new character from what the player set, saves it and paints its doll', async () => {
    const api = fakeApi();
    api.generate.mockReturnValue(
      stream({ type: 'call', purpose: 'character-biography' }, written()),
    );
    const editor = new Editor(context(api), Draft.blank());
    document.body.append(editor.root);

    type(field(editor.root, 'Name'), 'Wren Abernethy');
    buttonCalled(editor.root, 'Write character').click();
    await settle();

    expect(api.generate).toHaveBeenCalledWith(
      { source: 'player', name: 'Wren Abernethy' },
      expect.any(AbortSignal),
    );
    expect(editor.root.querySelector('.creator-status')?.textContent).toBe('Unsaved changes');
    expect(field(editor.root, 'How they come across').value).toBe(character().persona);

    buttonCalled(editor.root, 'Save').click();
    await settle();

    expect(api.create).toHaveBeenCalledWith(character());
    expect(api.submit).toHaveBeenCalledWith('doll', {
      character: 'wren_abernethy',
      appearance: character().appearance,
    });
    expect(editor.root.querySelector('.creator-status')?.textContent).toBe('Saved');
    expect(editor.root.querySelector('a[download]')?.getAttribute('href')).toBe(
      '/api/characters/wren_abernethy/export',
    );
  });

  it('rerolls a section, keeping what’s locked', async () => {
    const api = fakeApi();
    api.reroll.mockReturnValue(stream(written({ persona: 'Rerolled.' })));
    const editor = new Editor(context(api), Draft.of(character()));
    document.body.append(editor.root);
    const biography = editor.root.querySelector('[data-section="biography"]') as HTMLElement;
    const background = editor.root.querySelector('[data-section="background"]') as HTMLElement;

    buttonCalled(biography, 'Lock').click();
    buttonCalled(background, 'Reroll').click();
    await settle();

    expect(api.reroll).toHaveBeenCalledWith(
      character(),
      ['name', 'identity'],
      expect.any(AbortSignal),
    );
    expect(field(editor.root, 'How they come across').value).toBe('Rerolled.');
  });

  it('shows the verbal habits, and an edit locks them with the biography', async () => {
    const api = fakeApi();
    const habits = ['teases the people they like most', 'trails off mid-sentence'];
    const editor = new Editor(context(api), Draft.of(character({ mannerisms: habits })));
    document.body.append(editor.root);
    const biography = editor.root.querySelector('[data-section="biography"]') as HTMLElement;

    expect(field(editor.root, 'Verbal habits').value).toBe(habits.join('\n'));
    type(field(editor.root, 'Verbal habits'), ' asks "make sense?" after every explanation \n\n');
    expect(buttonCalled(biography, 'Locked').getAttribute('aria-pressed')).toBe('true');
    buttonCalled(editor.root, 'Save').click();
    await settle();

    expect(api.update).toHaveBeenCalledWith(
      character({ mannerisms: ['asks "make sense?" after every explanation'] }),
    );
  });

  it('won’t save what the server would refuse, and says why', async () => {
    const api = fakeApi();
    const editor = new Editor(context(api), Draft.of(character()));
    document.body.append(editor.root);

    type(field(editor.root, 'Name'), '');
    buttonCalled(editor.root, 'Save').click();
    await settle();

    expect(api.update).not.toHaveBeenCalled();
    expect(editor.root.querySelector('.creator-problems')?.textContent).toContain(
      'Give them a name.',
    );
  });

  it('shows the critic’s suggestions and applies one that’s accepted', async () => {
    const api = fakeApi();
    const suggestion = { field: 'persona', current: character().persona, suggested: 'Sharper.' };
    api.reroll.mockReturnValue(
      stream({ ...(written() as object), suggestions: [suggestion] } as GenerationEvent),
    );
    const editor = new Editor(context(api), Draft.of(character()));
    document.body.append(editor.root);

    buttonCalled(editor.root, 'Reroll unlocked').click();
    await settle();
    buttonCalled(editor.root, 'Accept').click();

    expect(field(editor.root, 'How they come across').value).toBe('Sharper.');
    expect(editor.root.querySelector('.creator-suggestion')).toBeNull();
  });

  it('ignores every suggestion at once', async () => {
    const api = fakeApi();
    const suggestions = [
      { field: 'persona', current: character().persona, suggested: 'Sharper.' },
      { field: 'backstory', current: character().backstory, suggested: 'Shorter.' },
    ];
    api.reroll.mockReturnValue(
      stream({ ...(written() as object), suggestions } as GenerationEvent),
    );
    const editor = new Editor(context(api), Draft.of(character()));
    document.body.append(editor.root);

    buttonCalled(editor.root, 'Reroll unlocked').click();
    await settle();
    buttonCalled(editor.root, 'Ignore all').click();

    expect(editor.root.querySelector('.creator-suggestion')).toBeNull();
    expect(field(editor.root, 'How they come across').value).toBe(character().persona);
    expect(editor.root.querySelector('.creator-status')?.textContent).toBe('Saved');
  });

  it('says the clip no longer matches a changed line, even once it’s saved', async () => {
    const api = fakeApi();
    const voiced = character({
      voice: { ...character().voice, reference_clip: 'clips/wren_abernethy.wav' },
    });
    const editor = new Editor(context(api), Draft.of(voiced));
    document.body.append(editor.root);
    const warning = () => editor.root.querySelector('.creator-voice > .creator-warn')?.textContent;

    type(field(editor.root, 'Their line'), 'A new line for the ferry.');
    buttonCalled(editor.root, 'Save').click();
    await settle();

    expect(api.update).toHaveBeenCalled();
    expect(warning()).toContain(`The voice clip says “${voiced.voice.reference_line}”`);
  });

  it('opens a premade character read-only', () => {
    const editor = new Editor(context(fakeApi()), Draft.of(character({ source: 'premade' })), true);
    expect(editor.root.querySelector('.creator-status')?.textContent).toBe('Premade, read-only');
    expect([...editor.root.querySelectorAll('button')].map((b) => b.textContent)).not.toContain(
      'Save',
    );
    expect(field(editor.root, 'Name').disabled).toBe(true);
  });

  it('previews the flat doll but paints none where the server can’t paint one', async () => {
    const api = fakeApi();
    const editor = new Editor(context(api, null), Draft.of(character()));
    document.body.append(editor.root);
    expect(editor.root.querySelector('.creator-doll')).not.toBeNull();

    type(field(editor.root, 'Name'), 'Wren Abernethy-Hale');
    buttonCalled(editor.root, 'Save').click();
    await settle();

    expect(api.update).toHaveBeenCalled();
    expect(api.submit).not.toHaveBeenCalled();
  });
});

describe('the library', () => {
  it('lists the player’s characters apart from the premade ones', async () => {
    const view = new LibraryView(fakeApi(), { open: vi.fn(), look: vi.fn(), imported: vi.fn() });
    await settle();
    const headings = [...view.root.querySelectorAll('h3')].map((h) => h.textContent);
    expect(headings).toEqual(['Yours 1', 'Premade 1, read-only']);
  });

  it('imports a file and opens what it imported', async () => {
    const api = fakeApi();
    const imported = vi.fn();
    const view = new LibraryView(api, { open: vi.fn(), look: vi.fn(), imported });
    const input = view.root.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(['zip'], 'wren.zip', { type: 'application/zip' });
    Object.defineProperty(input, 'files', { value: [file] });

    input.dispatchEvent(new Event('change'));
    await settle();

    expect(api.importFile).toHaveBeenCalledWith(file);
    expect(imported).toHaveBeenCalledWith(character({ id: 'wren_abernethy_2' }));
  });
});
