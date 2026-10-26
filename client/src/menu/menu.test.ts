// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  CheckedFeed,
  LibraryCharacter,
  MadeWorld,
  MakeWorld,
  MenuApi,
  NewsFeeds,
  NewWorld,
  Opening,
  SavedWorld,
  Worlds,
} from './api';
import { Menu } from './menu';

const character = (id: string, name: string): LibraryCharacter => ({
  id,
  name,
  birth_year: 1980,
  origin: 'Wales',
  occupation: 'Baker',
  persona: 'Up before dawn.',
  source: 'premade',
});

const LIBRARY = [
  character('ada_jones', 'Ada Jones'),
  character('ben_ross', 'Ben Ross'),
  character('cai_lewis', 'Cai Lewis'),
];

const saved = (id: string, name: string, changes: Partial<SavedWorld> = {}): SavedWorld => ({
  id,
  name,
  default: false,
  running: false,
  made: '2026-10-18T09:00:00Z',
  played: null,
  day: null,
  time: null,
  player: 'Visitor',
  residents: 3,
  ...changes,
});

const VILLAGE = saved('today', "Today's village", {
  default: true,
  running: true,
  day: 4,
  played: '2026-10-25T09:00:00Z',
  residents: 1,
});
const ASH = saved('2026-10-20-1000', 'Ash Lane', { day: 2, played: '2026-10-24T09:00:00Z' });

const TODAY: Worlds = {
  current: {
    id: 'today',
    name: "Today's village",
    default: true,
    data: 'data',
    residents: [{ id: 'kofi', name: 'Kofi', age: 30, occupation: 'Artist', home: 'house_1' }],
  },
  houses: 3,
  worlds: [VILLAGE, ASH],
  supervised: true,
};

const MADE: MadeWorld = {
  id: '2026-10-26-0900',
  name: 'Kiln Row',
  data: 'worlds/2026-10-26-0900',
  seed: 4,
  residents: [
    { id: 'ada_jones', name: 'Ada Jones', age: 46, occupation: 'Baker', home: 'house_2' },
    { id: 'ben_ross', name: 'Ben Ross', age: 46, occupation: 'Baker', home: 'house_1' },
  ],
  bonds: [{ kind: 'debt', actor: 'ben_ross', target: 'ada_jones', pinned: true }],
  missing: [{ id: 'ada_jones', name: 'Ada Jones', needs: ['voice', 'sprite'] }],
  restart: {
    env: { SIMILE_DB: 'worlds/2026-10-26-0900/simile.db' },
    command: 'SIMILE_DB=worlds/2026-10-26-0900/simile.db make dev',
  },
  opening: true,
};

const FEEDS: NewsFeeds = {
  feeds: [{ url: 'https://example.com/feed', name: 'Example', on: true, checked: null }],
  defaults: true,
  override: null,
  fetching: true,
  max: 12,
  calls_per_feed: 10,
};

const running = (id: string): Worlds => ({ ...TODAY, current: { ...TODAY.current, id } });

function fakeApi(changes: Partial<MenuApi> = {}) {
  return {
    worlds: vi.fn(async () => TODAY),
    characters: vi.fn(async () => LIBRARY),
    draw: vi.fn(async (asked: NewWorld) => [...asked.picks, 'cai_lewis']),
    create: vi.fn(async (asked: MakeWorld) => ({ ...MADE, name: asked.name ?? MADE.id })),
    open: vi.fn(async (id: string): Promise<Opening> => ({ id, opening: true })),
    rename: vi.fn(async (id: string, name: string) => ({ ...ASH, id, name })),
    remove: vi.fn(async () => {}),
    feeds: vi.fn(async () => FEEDS),
    checkFeed: vi.fn(async (): Promise<CheckedFeed> => Promise.reject(new Error('offline'))),
    addFeed: vi.fn(async () => FEEDS),
    switchFeed: vi.fn(async () => FEEDS),
    removeFeed: vi.fn(async () => FEEDS),
    resetFeeds: vi.fn(async () => FEEDS),
    ...changes,
  };
}

/** The title and the screen ask first; then the server restarts on `id`, down for a moment. */
function switchingTo(id: string) {
  return vi
    .fn<() => Promise<Worlds>>()
    .mockResolvedValueOnce(TODAY)
    .mockResolvedValueOnce(TODAY)
    .mockRejectedValueOnce(new TypeError('Failed to fetch'))
    .mockResolvedValueOnce(TODAY)
    .mockResolvedValue(running(id));
}

const settle = () => new Promise((resolve) => setTimeout(resolve));

const buttons = (root: HTMLElement) => [...root.querySelectorAll('button')];

function button(root: HTMLElement, text: string): HTMLButtonElement {
  const found = buttons(root).find((b) => b.textContent?.startsWith(text));
  if (!found) throw new Error(`No button ${text} in ${root.textContent}`);
  return found;
}

const card = (root: HTMLElement, name: string) =>
  [...root.querySelectorAll<HTMLButtonElement>('.menu-card')].find((c) =>
    c.textContent?.startsWith(name),
  )!;

const row = (root: HTMLElement, name: string) =>
  [...root.querySelectorAll<HTMLElement>('.menu-world')].find((r) =>
    r.querySelector('b')?.textContent?.startsWith(name),
  )!;

const heading = (root: HTMLElement) => root.querySelector('h2')?.textContent;

function press(target: Element, key: string) {
  target.dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true }));
}

function menuOn(api = fakeApi()) {
  const actions = { play: vi.fn(), enter: vi.fn() };
  const menu = new Menu(document.body, api, actions, { pollMs: 0, patienceMs: 50 });
  return { menu, api, actions, root: menu.root };
}

async function openNewGame(api = fakeApi()) {
  const opened = menuOn(api);
  button(opened.root, 'New game').click();
  await settle();
  return opened;
}

async function openLoadGame(api = fakeApi()) {
  const opened = menuOn(api);
  button(opened.root, 'Load game').click();
  await settle();
  return opened;
}

afterEach(() => document.body.replaceChildren());

describe('the title menu', () => {
  it('continues into the world the server is running', async () => {
    const { root, actions } = menuOn();
    await settle();

    const resume = button(root, 'Continue');
    expect(resume.textContent).toBe("ContinueToday's village · day 4 · 1 resident");
    expect(button(root, 'Load game').textContent).toContain('2 worlds');
    resume.click();
    expect(actions.play).toHaveBeenCalledOnce();
  });

  it('names a new world the server is running', async () => {
    const current = { ...TODAY.current, id: null, name: '2026-10-18-0900', default: false };
    const { root } = menuOn(fakeApi({ worlds: async () => ({ ...TODAY, current }) }));
    await settle();

    expect(button(root, 'Continue').textContent).toContain('World 2026-10-18-0900 · 1 resident');
  });

  it('still continues when the server is down', async () => {
    const worlds = async (): Promise<Worlds> => Promise.reject(new Error('offline'));
    const { root } = menuOn(fakeApi({ worlds }));
    await settle();

    expect(button(root, 'Continue').textContent).toContain("The server isn't answering yet");
    expect(button(root, 'Continue').disabled).toBe(false);
  });

  it('goes up and down its items with the arrow keys', () => {
    const { root } = menuOn();
    expect(document.activeElement).toBe(button(root, 'Continue'));

    press(document.activeElement!, 'ArrowDown');
    expect(document.activeElement).toBe(button(root, 'New game'));
    press(document.activeElement!, 'ArrowDown');
    press(document.activeElement!, 'ArrowDown');
    expect(document.activeElement).toBe(button(root, 'News feeds'));
    press(document.activeElement!, 'ArrowDown');
    expect(document.activeElement).toBe(button(root, 'Continue'));
    press(document.activeElement!, 'ArrowUp');
    expect(document.activeElement).toBe(button(root, 'News feeds'));
  });

  it('opens the creator only when the client has one', () => {
    const without = menuOn();
    expect(button(without.root, 'Characters').disabled).toBe(true);

    const creator = vi.fn();
    const withIt = new Menu(document.body, fakeApi(), { play: vi.fn(), enter: vi.fn(), creator });
    button(withIt.root, 'Characters').click();
    expect(creator).toHaveBeenCalledOnce();
  });

  it('opens the news feeds and comes back, by Back or Esc', async () => {
    const { root, actions } = menuOn();

    button(root, 'News feeds').click();
    await settle();
    expect(heading(root)).toBe('News feeds');
    button(root, 'Back').click();
    expect(button(root, 'Continue')).toBeTruthy();

    button(root, 'News feeds').click();
    await settle();
    press(root, 'Escape');
    expect(button(root, 'Continue')).toBeTruthy();
    expect(actions.play).not.toHaveBeenCalled();
  });

  it('says when it can’t list the feeds', async () => {
    const feeds = async (): Promise<NewsFeeds> => Promise.reject(new Error('offline'));
    const { root } = menuOn(fakeApi({ feeds }));

    button(root, 'News feeds').click();
    await settle();

    expect(root.querySelector('.menu-error')?.textContent).toBe(
      "Couldn't list the feeds: offline",
    );
    button(root, 'Back').click();
    expect(button(root, 'Continue')).toBeTruthy();
  });
});

describe('New game', () => {
  it('shows the library, how many houses there are and a name to start with', async () => {
    const { root } = await openNewGame();

    expect(heading(root)).toBe('New game');
    expect([...root.querySelectorAll('.menu-card b')].map((b) => b.textContent)).toEqual([
      'Ada Jones',
      'Ben Ross',
      'Cai Lewis',
    ]);
    expect(root.querySelector('.menu-count-value')?.textContent).toBe('3');
    expect(root.textContent).toContain('of 3 houses');
    expect(root.querySelector<HTMLInputElement>('.menu-name-input')!.value).toMatch(/^\w+ \w+$/);
    expect(document.activeElement).toBe(button(root, 'Start'));
  });

  it('makes a world in one click, opens it and goes into it once the server runs it', async () => {
    const api = fakeApi({ worlds: switchingTo(MADE.id) });
    const { root, actions } = await openNewGame(api);
    const name = root.querySelector<HTMLInputElement>('.menu-name-input')!.value;

    button(root, 'Start').click();
    expect(heading(root)).toBe(`Making ${name}`);
    await vi.waitFor(() => expect(actions.enter).toHaveBeenCalledOnce());

    expect(api.create).toHaveBeenCalledWith({ count: 3, picks: [], pins: [], name, open: true });
    expect(heading(root)).toBe(`Opening ${name}`);
    expect(root.querySelector('[role=status]')?.textContent).toBe('Ready.');
    expect(actions.play).not.toHaveBeenCalled();
  });

  it('starts a named world of the residents picked, with a pinned bond', async () => {
    const api = fakeApi({ worlds: switchingTo(MADE.id) });
    const { root, actions } = await openNewGame(api);
    root.querySelector<HTMLInputElement>('.menu-name-input')!.value = '  Kiln Row ';
    button(root, '−').click();
    card(root, 'Ada Jones').click();
    card(root, 'Ben Ross').click();
    expect(card(root, 'Ada Jones').dataset.state).toBe('picked');
    expect(root.querySelector('.menu-summary')?.textContent).toBe('2 picked.');

    const [actor, kind, target] = root.querySelectorAll('select');
    actor.value = 'ben_ross';
    kind.value = 'debt';
    target.value = 'ada_jones';
    button(root, 'Pin').click();
    expect(root.querySelector('.menu-pins')?.textContent).toContain(
      'Ben Ross owes money to Ada Jones',
    );

    root.querySelector('form')!.requestSubmit();
    await vi.waitFor(() => expect(actions.enter).toHaveBeenCalledOnce());

    expect(api.create).toHaveBeenCalledWith({
      count: 2,
      picks: ['ada_jones', 'ben_ross'],
      pins: [{ kind: 'debt', actor: 'ben_ross', target: 'ada_jones' }],
      name: 'Kiln Row',
      open: true,
    });
  });

  it('randomises the houses still open', async () => {
    const { root, api } = await openNewGame();
    card(root, 'Ben Ross').click();

    button(root, 'Randomise').click();
    await settle();

    expect(api.draw).toHaveBeenCalledWith({ count: 3, picks: ['ben_ross'], pins: [] });
    expect(card(root, 'Ben Ross').dataset.state).toBe('picked');
    expect(card(root, 'Cai Lewis').dataset.state).toBe('drawn');
    expect(root.querySelector('.menu-summary')?.textContent).toBe(
      '1 picked, 1 drawn, 1 more drawn at random when it starts.',
    );
  });

  it('only offers bonds once two residents are in', async () => {
    const { root } = await openNewGame();
    const form = root.querySelector<HTMLElement>('.menu-pin-form')!;
    expect(form.hidden).toBe(true);

    card(root, 'Ada Jones').click();
    card(root, 'Cai Lewis').click();

    expect(form.hidden).toBe(false);
    expect([...root.querySelectorAll('select')].map((s) => s.value)).toEqual([
      'ada_jones',
      'old_friend',
      'cai_lewis',
    ]);
  });

  it('shows the server’s reason when it refuses, and stays put', async () => {
    const create = async (): Promise<MadeWorld> => Promise.reject(new Error('No character x'));
    const { root } = await openNewGame(fakeApi({ create }));
    card(root, 'Ada Jones').click();

    button(root, 'Start').click();
    await settle();

    expect(root.querySelector('[role=alert]')?.textContent).toBe('No character x');
    expect(heading(root)).toBe('New game');
    expect(card(root, 'Ada Jones').dataset.state).toBe('picked');
    expect(button(root, 'Start').disabled).toBe(false);
  });

  it('says so when the server doesn’t come back on the new world', async () => {
    const { root, actions } = await openNewGame();

    button(root, 'Start').click();
    await vi.waitFor(() => expect(root.querySelector('.menu-error')).toBeTruthy());

    expect(root.querySelector('.menu-error')?.textContent).toMatch(
      /didn't come back on it within .* The terminal running make dev says why\./,
    );
    expect(actions.enter).not.toHaveBeenCalled();
    button(root, 'Back').click();
    expect(button(root, 'Continue')).toBeTruthy();
  });
});

describe('a new world the server can’t switch to', () => {
  it('reports what is missing and how to start the server on it', async () => {
    const create = vi.fn(async () => ({ ...MADE, opening: false }));
    const { root, actions } = await openNewGame(fakeApi({ create }));
    button(root, 'Start').click();
    await settle();

    const text = root.textContent!;
    expect(heading(root)).toBe('Your new world is ready');
    expect(text).toContain('World Kiln Row, in server/worlds/2026-10-26-0900');
    expect(text).toContain('Ben Ross owes money to Ada Jones');
    expect(text).toContain('No voice recorded yet for Ada Jones');
    expect(text).toContain('No sprite yet for Ada Jones');
    expect(root.querySelector('.menu-command code')?.textContent).toBe(MADE.restart.command);
    expect(actions.enter).not.toHaveBeenCalled();

    button(root, 'Back to the menu').click();
    expect(button(root, 'Continue')).toBeTruthy();
  });
});

describe('Load game', () => {
  it('lists every world with its day, when it was played and who plays it', async () => {
    const { root } = await openLoadGame();

    expect(heading(root)).toBe('Load game');
    const village = row(root, "Today's village");
    expect(village.querySelector('.menu-world-name')?.textContent).toBe("Today's villageplaying");
    expect(village.textContent).toContain('day 4 · played');
    expect(village.querySelector('.menu-world-kept')?.textContent).toBe(
      "Today's village is kept: it can't be deleted.",
    );
    expect(row(root, 'Ash Lane').querySelector('.menu-world-kept')).toBeNull();
    expect(row(root, 'Ash Lane').querySelector('small')?.textContent).toMatch(
      /^day 2 · played .+ · Visitor · 3 residents$/,
    );
    expect(document.activeElement).toBe(village.querySelector('.menu-world-open'));
  });

  it('opens a world and goes into it once the server runs it', async () => {
    const api = fakeApi({ worlds: switchingTo(ASH.id) });
    const { root, actions } = await openLoadGame(api);

    row(root, 'Ash Lane').querySelector<HTMLButtonElement>('.menu-world-open')!.click();
    expect(heading(root)).toBe('Opening Ash Lane');
    await vi.waitFor(() => expect(actions.enter).toHaveBeenCalledOnce());

    expect(api.open).toHaveBeenCalledWith(ASH.id);
    expect(vi.mocked(api.worlds).mock.calls.length).toBeGreaterThanOrEqual(5);
  });

  it('continues the world it’s in rather than opening it again', async () => {
    const { root, api, actions } = await openLoadGame();

    row(root, "Today's village").querySelector<HTMLButtonElement>('.menu-world-open')!.click();

    expect(actions.play).toHaveBeenCalledOnce();
    expect(api.open).not.toHaveBeenCalled();
  });

  it('goes into a world the server turns out to be running already', async () => {
    const open = vi.fn(async (id: string): Promise<Opening> => ({ id, opening: false }));
    const api = fakeApi({ open });
    const { root, actions } = await openLoadGame(api);

    row(root, 'Ash Lane').querySelector<HTMLButtonElement>('.menu-world-open')!.click();
    await settle();

    expect(open).toHaveBeenCalledWith(ASH.id);
    expect(actions.enter).toHaveBeenCalledOnce();
    expect(api.worlds).toHaveBeenCalledTimes(2);
  });

  it('says why it can’t open a world', async () => {
    const open = async (): Promise<Opening> => Promise.reject(new Error('No world x'));
    const { root } = await openLoadGame(fakeApi({ open }));

    row(root, 'Ash Lane').querySelector<HTMLButtonElement>('.menu-world-open')!.click();
    await settle();

    expect(root.querySelector('.menu-error')?.textContent).toBe("Couldn't open Ash Lane: No world x");
    button(root, 'Back').click();
    await settle();
    expect(heading(root)).toBe('Load game');
  });

  it('says when the server can’t switch worlds, and only continues', async () => {
    const { root } = await openLoadGame(
      fakeApi({ worlds: async () => ({ ...TODAY, supervised: false }) }),
    );

    expect(root.querySelector('.menu-note')?.textContent).toContain('make dev');
    const open = (name: string) =>
      row(root, name).querySelector<HTMLButtonElement>('.menu-world-open')!;
    expect(open('Ash Lane').disabled).toBe(true);
    expect(open("Today's village").disabled).toBe(false);
  });

  it('renames a world', async () => {
    const { root, api } = await openLoadGame();

    button(row(root, 'Ash Lane'), 'Rename').click();
    const input = root.querySelector<HTMLInputElement>('.menu-world-rename input')!;
    expect(document.activeElement).toBe(input);
    expect(input.value).toBe('Ash Lane');
    input.value = 'Rook Yard';
    input.form!.requestSubmit();
    await settle();

    expect(api.rename).toHaveBeenCalledWith(ASH.id, 'Rook Yard');
    expect(row(root, 'Rook Yard')).toBeTruthy();
    expect(document.activeElement).toBe(row(root, 'Rook Yard').querySelector('.menu-world-open'));
  });

  it('leaves the name alone on Esc, without leaving the list', async () => {
    const { root, api } = await openLoadGame();

    button(row(root, 'Ash Lane'), 'Rename').click();
    const input = root.querySelector<HTMLInputElement>('.menu-world-rename input')!;
    input.value = 'Rook Yard';
    press(input, 'Escape');

    expect(api.rename).not.toHaveBeenCalled();
    expect(heading(root)).toBe('Load game');
    expect(row(root, 'Ash Lane')).toBeTruthy();
  });

  it('deletes a world once confirmed', async () => {
    const { root, api } = await openLoadGame();

    button(row(root, 'Ash Lane'), 'Delete').click();
    expect(root.textContent).toContain('Delete Ash Lane for good?');
    expect(document.activeElement?.textContent).toBe('Keep it');
    button(root, 'Keep it').click();
    expect(api.remove).not.toHaveBeenCalled();

    button(row(root, 'Ash Lane'), 'Delete').click();
    button(root.querySelector('.menu-world-confirm')!, 'Delete').click();
    await settle();

    expect(api.remove).toHaveBeenCalledWith(ASH.id);
    expect(row(root, 'Ash Lane')).toBeUndefined();
  });

  it('keeps today’s village and the world it’s in', async () => {
    const { root } = await openLoadGame(
      fakeApi({
        worlds: async () => ({
          ...TODAY,
          worlds: [{ ...VILLAGE, running: false }, { ...ASH, running: true }],
        }),
      }),
    );

    const remove = (name: string) => button(row(root, name), 'Delete');
    const reason = (name: string) =>
      document.getElementById(remove(name).getAttribute('aria-describedby')!)?.textContent;
    expect(remove("Today's village").disabled).toBe(true);
    expect(reason("Today's village")).toContain("can't be deleted");
    expect(remove('Ash Lane').disabled).toBe(true);
    expect(reason('Ash Lane')).toBe("You're in it: load another world to delete it.");
  });

  it('shows the server’s reason when it won’t delete', async () => {
    const remove = async () => Promise.reject(new Error('Not while it runs'));
    const { root } = await openLoadGame(fakeApi({ remove }));

    button(row(root, 'Ash Lane'), 'Delete').click();
    button(root.querySelector('.menu-world-confirm')!, 'Delete').click();
    await settle();

    expect(root.querySelector('[role=alert]')?.textContent).toBe('Not while it runs');
    expect(row(root, 'Ash Lane')).toBeTruthy();
  });
});
