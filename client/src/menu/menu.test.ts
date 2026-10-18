// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import type {
  CheckedFeed,
  LibraryCharacter,
  MadeWorld,
  MenuApi,
  NewsFeeds,
  NewWorld,
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

const TODAY: Worlds = {
  current: {
    name: "Today's village",
    default: true,
    data: 'data',
    residents: [{ id: 'kofi', name: 'Kofi', age: 30, occupation: 'Artist', home: 'house_1' }],
  },
  houses: 3,
};

const MADE: MadeWorld = {
  name: '2026-10-18-0900',
  data: 'worlds/2026-10-18-0900',
  seed: 4,
  residents: [
    { id: 'ada_jones', name: 'Ada Jones', age: 46, occupation: 'Baker', home: 'house_2' },
    { id: 'ben_ross', name: 'Ben Ross', age: 46, occupation: 'Baker', home: 'house_1' },
  ],
  bonds: [{ kind: 'debt', actor: 'ben_ross', target: 'ada_jones', pinned: true }],
  missing: [{ id: 'ada_jones', name: 'Ada Jones', needs: ['voice', 'sprite'] }],
  restart: {
    env: { SIMILE_DB: 'worlds/2026-10-18-0900/simile.db' },
    command: 'SIMILE_DB=worlds/2026-10-18-0900/simile.db make dev',
  },
};

const FEEDS: NewsFeeds = {
  feeds: [{ url: 'https://example.com/feed', name: 'Example', on: true, checked: null }],
  defaults: true,
  override: null,
  fetching: true,
  max: 12,
  calls_per_feed: 10,
};

function fakeApi(changes: Partial<MenuApi> = {}) {
  return {
    worlds: vi.fn(async () => TODAY),
    characters: vi.fn(async () => LIBRARY),
    draw: vi.fn(async (asked: NewWorld) => [...asked.picks, 'cai_lewis']),
    create: vi.fn(async () => MADE),
    feeds: vi.fn(async () => FEEDS),
    checkFeed: vi.fn(async (): Promise<CheckedFeed> => Promise.reject(new Error('offline'))),
    addFeed: vi.fn(async () => FEEDS),
    switchFeed: vi.fn(async () => FEEDS),
    removeFeed: vi.fn(async () => FEEDS),
    resetFeeds: vi.fn(async () => FEEDS),
    ...changes,
  };
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

async function openNewWorld(api = fakeApi()) {
  const menu = new Menu(document.body, api, { play: vi.fn() });
  button(menu.root, 'New world').click();
  await settle();
  return { menu, api, root: menu.root };
}

afterEach(() => document.body.replaceChildren());

describe('the title menu', () => {
  it('continues into the world the server is running', async () => {
    const play = vi.fn();
    const menu = new Menu(document.body, fakeApi(), { play });
    await settle();

    const resume = button(menu.root, 'Continue');
    expect(resume.textContent).toBe("ContinueToday's village · 1 resident");
    resume.click();
    expect(play).toHaveBeenCalledOnce();
  });

  it('names a new world the server is running', async () => {
    const current = { ...TODAY.current, name: '2026-10-18-0900', default: false };
    const menu = new Menu(document.body, fakeApi({ worlds: async () => ({ ...TODAY, current }) }), {
      play: vi.fn(),
    });
    await settle();

    expect(button(menu.root, 'Continue').textContent).toContain(
      'World 2026-10-18-0900 · 1 resident',
    );
  });

  it('still continues when the server is down', async () => {
    const worlds = async (): Promise<Worlds> => Promise.reject(new Error('offline'));
    const menu = new Menu(document.body, fakeApi({ worlds }), { play: vi.fn() });
    await settle();

    expect(button(menu.root, 'Continue').textContent).toContain("The server isn't answering yet");
    expect(button(menu.root, 'Continue').disabled).toBe(false);
  });

  it('opens the creator only when the client has one', () => {
    const without = new Menu(document.body, fakeApi(), { play: vi.fn() });
    expect(button(without.root, 'Characters').disabled).toBe(true);

    const creator = vi.fn();
    const withIt = new Menu(document.body, fakeApi(), { play: vi.fn(), creator });
    button(withIt.root, 'Characters').click();
    expect(creator).toHaveBeenCalledOnce();
  });

  it('opens the news feeds and comes back', async () => {
    const play = vi.fn();
    const menu = new Menu(document.body, fakeApi(), { play });

    button(menu.root, 'News feeds').click();
    await settle();
    expect(menu.root.querySelector('h2')?.textContent).toBe('News feeds');

    button(menu.root, 'Back').click();
    expect(button(menu.root, 'Continue')).toBeTruthy();
    expect(play).not.toHaveBeenCalled();
  });

  it('says when it can’t list the feeds', async () => {
    const feeds = async (): Promise<NewsFeeds> => Promise.reject(new Error('offline'));
    const menu = new Menu(document.body, fakeApi({ feeds }), { play: vi.fn() });

    button(menu.root, 'News feeds').click();
    await settle();

    expect(menu.root.querySelector('.menu-error')?.textContent).toBe(
      "Couldn't list the feeds: offline",
    );
    button(menu.root, 'Back').click();
    expect(button(menu.root, 'Continue')).toBeTruthy();
  });
});

describe('the New world screen', () => {
  it('shows the library and how many houses there are', async () => {
    const { root } = await openNewWorld();

    expect([...root.querySelectorAll('.menu-card b')].map((b) => b.textContent)).toEqual([
      'Ada Jones',
      'Ben Ross',
      'Cai Lewis',
    ]);
    expect(root.querySelector('.menu-count-value')?.textContent).toBe('3');
    expect(root.textContent).toContain('of 3 houses');
  });

  it('starts a world of the residents picked, with a pinned bond', async () => {
    const { root, api } = await openNewWorld();
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

    button(root, 'Start').click();
    await settle();

    expect(api.create).toHaveBeenCalledWith({
      count: 2,
      picks: ['ada_jones', 'ben_ross'],
      pins: [{ kind: 'debt', actor: 'ben_ross', target: 'ada_jones' }],
    });
    expect(root.querySelector('h2')?.textContent).toBe('Your new world is ready');
  });

  it('randomises the houses still open', async () => {
    const { root, api } = await openNewWorld();
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
    const { root } = await openNewWorld();
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
    const { root } = await openNewWorld(fakeApi({ create }));

    button(root, 'Start').click();
    await settle();

    expect(root.querySelector('[role=alert]')?.textContent).toBe('No character x');
    expect(root.querySelector('h2')?.textContent).toBe('New world');
    expect(button(root, 'Start').disabled).toBe(false);
  });
});

describe('the ready screen', () => {
  it('reports what is missing and how to start the server on the new world', async () => {
    const { root } = await openNewWorld();
    button(root, 'Start').click();
    await settle();

    const text = root.textContent!;
    expect(text).toContain('World 2026-10-18-0900, in server/worlds/2026-10-18-0900');
    expect(text).toContain('Ben Ross owes money to Ada Jones');
    expect(text).toContain('No voice recorded yet for Ada Jones');
    expect(text).toContain('No sprite yet for Ada Jones');
    expect(root.querySelector('.menu-command code')?.textContent).toBe(MADE.restart.command);

    button(root, 'Back to the menu').click();
    expect(button(root, 'Continue')).toBeTruthy();
  });
});
