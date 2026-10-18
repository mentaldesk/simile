// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { CheckedFeed, MenuApi, NewsFeed, NewsFeeds } from './api';
import { Menu } from './menu';
import { ago, usageNote } from './news-feeds';

const NOW = Date.parse('2026-10-18T12:00:00Z');
const minutesAgo = (n: number) => (NOW - n * 60_000) / 1000;

const ATLANTIC: NewsFeed = {
  url: 'https://www.theatlantic.com/feed/best-of/',
  name: 'The Atlantic',
  on: true,
  checked: minutesAgo(12),
};
const RNZ: NewsFeed = {
  url: 'https://www.rnz.co.nz/rss/sport.xml',
  name: 'RNZ Sport',
  on: true,
  checked: null,
};
const BIG_THINK: CheckedFeed = {
  url: 'https://bigthink.com/feed',
  title: 'Big Think',
  latest: {
    title: 'A new window to the early universe',
    published: new Date(NOW - 3 * 3600_000).toISOString(),
  },
};

/** The server's list, in memory, refusing what it would. */
class FakeFeeds {
  feeds: NewsFeed[] = [ATLANTIC, RNZ];
  listing: Omit<NewsFeeds, 'feeds' | 'defaults'> = {
    override: null,
    fetching: true,
    max: 12,
    calls_per_feed: 10,
  };
  defaults = true;

  current(): NewsFeeds {
    const feeds = this.feeds.map((feed) => ({ ...feed }));
    return { ...this.listing, feeds, defaults: this.defaults };
  }

  changed(feeds: NewsFeed[]): NewsFeeds {
    this.feeds = feeds;
    this.defaults = false;
    return this.current();
  }

  api() {
    const api: MenuApi = {
      worlds: vi.fn(() => new Promise<never>(() => {})),
      characters: vi.fn(),
      draw: vi.fn(),
      create: vi.fn(),
      feeds: vi.fn(async () => this.current()),
      checkFeed: vi.fn(async (url: string) => {
        if (url !== BIG_THINK.url) throw new Error("That's a web page, not a feed");
        return BIG_THINK;
      }),
      addFeed: vi.fn(async (url: string) =>
        this.changed([...this.feeds, { url, name: 'Big Think', on: true, checked: null }]),
      ),
      switchFeed: vi.fn(async (url: string, on: boolean) =>
        this.changed(this.feeds.map((feed) => (feed.url === url ? { ...feed, on } : feed))),
      ),
      removeFeed: vi.fn(async (url: string) =>
        this.changed(this.feeds.filter((feed) => feed.url !== url)),
      ),
      resetFeeds: vi.fn(async () => {
        this.feeds = [ATLANTIC, RNZ];
        this.defaults = true;
        return this.current();
      }),
    };
    return api;
  }
}

const settle = () => new Promise((resolve) => setTimeout(resolve));

function button(root: HTMLElement, text: string): HTMLButtonElement {
  const found = [...root.querySelectorAll('button')].find((b) => b.textContent === text);
  if (!found) throw new Error(`No button ${text} in ${root.textContent}`);
  return found;
}

const rows = (root: HTMLElement) => [...root.querySelectorAll<HTMLElement>('.menu-feed')];

const names = (root: HTMLElement) => rows(root).map((row) => row.querySelector('b')?.textContent);

const switchOf = (root: HTMLElement, name: string) =>
  root.querySelector<HTMLButtonElement>(`[role=switch][aria-label="Read ${name}"]`)!;

async function open(server = new FakeFeeds()) {
  const api = server.api();
  const menu = new Menu(document.body, api, { play: vi.fn() });
  button(menu.root, 'News feedsChoose what the village reads').click();
  await settle();
  return { root: menu.root, api, server };
}

async function check(root: HTMLElement, url: string) {
  const input = root.querySelector<HTMLInputElement>('.menu-url')!;
  input.value = url;
  root.querySelector('form')!.requestSubmit();
  await settle();
}

beforeEach(() => {
  vi.useFakeTimers({ toFake: ['Date'] });
  vi.setSystemTime(NOW);
});

afterEach(() => {
  vi.useRealTimers();
  document.body.replaceChildren();
});

describe('the News feeds screen', () => {
  it('lists each feed with its name, URL, switch and when it last fetched', async () => {
    const { root } = await open();

    expect(names(root)).toEqual(['The Atlantic', 'RNZ Sport']);
    const [atlantic, rnz] = rows(root);
    expect(atlantic.querySelector('.menu-feed-url')?.textContent).toBe(ATLANTIC.url);
    expect(atlantic.querySelector('.menu-feed-checked')?.textContent).toBe('fetched 12 min ago');
    expect(rnz.querySelector('.menu-feed-checked')?.textContent).toBe('not fetched yet');
    expect(switchOf(root, 'The Atlantic').getAttribute('aria-checked')).toBe('true');
    expect(root.querySelector('footer')?.textContent).toContain('2 feeds of 12, 2 on');
  });

  it('says what the feeds cost under the list', async () => {
    const { root } = await open();

    expect(root.querySelector('.menu-usage')?.textContent).toBe(
      "Each feed that's on adds up to 10 Haiku calls when its new stories are analysed, " +
        'so up to 20 at once with 2 on. The list takes at most 12.',
    );
  });

  it('switches a feed off and back on', async () => {
    const { root, api } = await open();

    switchOf(root, 'RNZ Sport').click();
    await settle();

    expect(api.switchFeed).toHaveBeenCalledWith(RNZ.url, false);
    expect(switchOf(root, 'RNZ Sport').getAttribute('aria-checked')).toBe('false');
    expect(rows(root)[1].dataset.on).toBe('false');
    expect(root.querySelector('.menu-usage')?.textContent).toContain('up to 10 at once with 1 on');

    switchOf(root, 'RNZ Sport').click();
    await settle();
    expect(api.switchFeed).toHaveBeenLastCalledWith(RNZ.url, true);
    expect(switchOf(root, 'RNZ Sport').getAttribute('aria-checked')).toBe('true');
  });

  it('removes a feed', async () => {
    const { root, api } = await open();

    rows(root)[0].querySelector<HTMLButtonElement>('.menu-remove')!.click();
    await settle();

    expect(api.removeFeed).toHaveBeenCalledWith(ATLANTIC.url);
    expect(names(root)).toEqual(['RNZ Sport']);
  });

  it('checks a pasted URL and shows its title and latest headline before adding it', async () => {
    const { root, api } = await open();

    await check(root, `  ${BIG_THINK.url} `);

    expect(api.checkFeed).toHaveBeenCalledWith(BIG_THINK.url);
    expect(api.addFeed).not.toHaveBeenCalled();
    const preview = root.querySelector<HTMLElement>('.menu-preview')!;
    expect(preview.hidden).toBe(false);
    expect(preview.querySelector('b')?.textContent).toBe('Big Think');
    expect(preview.querySelector('.menu-latest')?.textContent).toBe(
      'Latest: “A new window to the early universe”, 3 hours ago',
    );

    button(root, 'Add').click();
    await settle();

    expect(api.addFeed).toHaveBeenCalledWith(BIG_THINK.url);
    expect(names(root)).toEqual(['The Atlantic', 'RNZ Sport', 'Big Think']);
    expect(preview.hidden).toBe(true);
    expect(root.querySelector<HTMLInputElement>('.menu-url')?.value).toBe('');
  });

  it('drops the preview when the URL changes or on Cancel', async () => {
    const { root } = await open();
    const preview = root.querySelector<HTMLElement>('.menu-preview')!;

    await check(root, BIG_THINK.url);
    button(root, 'Cancel').click();
    expect(preview.hidden).toBe(true);

    await check(root, BIG_THINK.url);
    root.querySelector('.menu-url')!.dispatchEvent(new Event('input'));
    expect(preview.hidden).toBe(true);
  });

  it('shows why the server refused a URL, and adds nothing', async () => {
    const { root, api } = await open();

    await check(root, 'https://example.com/');

    expect(root.querySelector('[role=alert]')?.textContent).toBe("That's a web page, not a feed");
    expect(root.querySelector<HTMLElement>('.menu-preview')?.hidden).toBe(true);
    expect(api.addFeed).not.toHaveBeenCalled();
    expect(button(root, 'Check').disabled).toBe(false);
  });

  it('stops taking feeds when the list is full', async () => {
    const server = new FakeFeeds();
    server.listing.max = 2;
    const { root } = await open(server);

    expect(root.querySelector<HTMLInputElement>('.menu-url')?.disabled).toBe(true);
    expect(button(root, 'Check').disabled).toBe(true);
    expect(root.querySelector<HTMLInputElement>('.menu-url')?.placeholder).toBe(
      'The list is full. Remove a feed to add another.',
    );

    rows(root)[0].querySelector<HTMLButtonElement>('.menu-remove')!.click();
    await settle();
    expect(button(root, 'Check').disabled).toBe(false);
  });

  it('resets to the defaults on a second click', async () => {
    const { root, api } = await open();
    expect(button(root, 'Reset to defaults').disabled).toBe(true);

    switchOf(root, 'RNZ Sport').click();
    await settle();
    const reset = button(root, 'Reset to defaults');
    expect(reset.disabled).toBe(false);

    reset.click();
    expect(reset.textContent).toBe('Really reset?');
    expect(api.resetFeeds).not.toHaveBeenCalled();

    reset.click();
    await settle();
    expect(api.resetFeeds).toHaveBeenCalledOnce();
    expect(switchOf(root, 'RNZ Sport').getAttribute('aria-checked')).toBe('true');
    expect(reset.textContent).toBe('Reset to defaults');
    expect(reset.disabled).toBe(true);
  });

  it('says when the env overrides the list, or news is off', async () => {
    const server = new FakeFeeds();
    server.listing.override = ['https://example.com/a'];
    server.listing.fetching = false;
    const { root } = await open(server);

    expect([...root.querySelectorAll('.menu-note')].map((note) => note.textContent)).toEqual([
      "This run reads SIMILE_NEWS_FEED's 1 feed instead. Changes here apply once it's unset.",
      'News is off for this run (SIMILE_NEWS=0), so nothing is fetched.',
    ]);
  });

  it('says so when every feed is gone', async () => {
    const server = new FakeFeeds();
    server.feeds = [];
    const { root } = await open(server);

    expect(root.querySelector('.menu-feeds')?.textContent).toBe(
      'No feeds. The terminals keep the stories they have.',
    );
    expect(root.querySelector('.menu-usage')?.textContent).toBe(
      "Each feed that's on adds up to 10 Haiku calls when its new stories are analysed. " +
        'The list takes at most 12.',
    );
  });

  it('shows a failed change and keeps the list', async () => {
    const server = new FakeFeeds();
    const api = server.api();
    api.removeFeed = vi.fn(async () => Promise.reject(new Error("That feed isn't in the list")));
    const menu = new Menu(document.body, api, { play: vi.fn() });
    await menu.newsFeeds();

    rows(menu.root)[0].querySelector<HTMLButtonElement>('.menu-remove')!.click();
    await settle();

    expect(menu.root.querySelector('[role=alert]')?.textContent).toBe(
      "That feed isn't in the list",
    );
    expect(names(menu.root)).toEqual(['The Atlantic', 'RNZ Sport']);
  });
});

describe('ago', () => {
  it('says how long ago in a few words', () => {
    const before = (ms: number) => ago(NOW - ms, NOW);

    expect(before(20_000)).toBe('just now');
    expect(before(5 * 60_000)).toBe('5 min ago');
    expect(before(3600_000)).toBe('1 hour ago');
    expect(before(5 * 3600_000)).toBe('5 hours ago');
    expect(before(2 * 86400_000)).toBe('2 days ago');
    expect(ago(Date.parse('2021-09-15T16:00:00Z'), NOW)).toBe('on 2021-09-15');
    expect(ago(NOW + 60_000, NOW)).toBe('just now');
  });
});

describe('usageNote', () => {
  it('counts only the feeds that are on', () => {
    const listing = new FakeFeeds().current();
    listing.feeds[0].on = false;

    expect(usageNote(listing)).toContain('so up to 10 at once with 1 on');
  });
});
