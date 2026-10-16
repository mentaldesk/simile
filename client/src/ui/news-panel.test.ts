// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi, type MockInstance } from 'vitest';
import { server, type NewsArticle } from '../net';
import { NewsPanel } from './news-panel';

const ARTICLES: NewsArticle[] = [
  {
    news_id: 'barrier',
    title: 'Tidal barrier for the river',
    source: 'The Atlantic',
    summary: 'The council votes for a barrier.',
    url: 'https://example.com/barrier',
    read: false,
  },
  {
    news_id: 'bees',
    title: 'Bees in decline',
    source: '',
    summary: 'Fewer bees than ever.',
    url: 'https://example.com/bees',
    read: true,
  },
];

let panel: NewsPanel;
let send: MockInstance<typeof server.send>;

const section = () => document.querySelector<HTMLElement>('.news')!;
const items = () => [...document.querySelectorAll<HTMLElement>('.news li')];
const titles = () => items().map((item) => item.querySelector('b')!.textContent);
const selected = () => document.querySelector('.news-selected b')?.textContent;
const status = () => document.querySelector('.news > p')!.textContent;
const link = () => document.querySelector<HTMLAnchorElement>('.news a');

function news(articles: NewsArticle[]): void {
  server.dispatch(JSON.stringify({ type: 'news', articles }));
}

function press(key: string, init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init });
  (document.activeElement ?? section()).dispatchEvent(event);
  return event;
}

beforeEach(() => {
  send = vi.spyOn(server, 'send').mockReturnValue(true);
  panel = new NewsPanel(document.body, server);
});

afterEach(() => {
  panel.stop();
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

it('asks for the news when it opens, and lists it with titles, sources and summaries', () => {
  panel.open('News terminal on the square');

  expect(send).toHaveBeenCalledWith({ type: 'list_news' });
  expect(document.querySelector('.news header b')!.textContent).toBe('News terminal on the square');
  expect(status()).toBe('Loading the news…');
  expect(document.activeElement).toBe(section());

  news(ARTICLES);

  expect(status()).toBe('');
  expect(titles()).toEqual(['Tidal barrier for the river', 'Bees in decline']);
  expect(items()[0].querySelector('small')!.textContent).toBe('The Atlantic');
  expect(items()[1].querySelector('small')).toBeNull();
  expect(items()[0].querySelector('p')!.textContent).toBe('The council votes for a barrier.');
  expect(items().map((item) => item.classList.contains('news-read'))).toEqual([false, true]);
  expect(selected()).toBe('Tidal barrier for the river');
  expect(link()).toBeNull();
});

it('ignores the news while closed', () => {
  news(ARTICLES);
  expect(items()).toEqual([]);

  panel.open('Terminal');
  panel.close();
  news(ARTICLES);
  expect(items()).toEqual([]);
});

it('says when there is no news, or no connection', () => {
  panel.open('Terminal');
  news([]);
  expect(status()).toBe('No news yet.');

  send.mockReturnValue(false);
  panel.close();
  panel.open('Terminal');
  expect(status()).toBe('Not connected, so there’s no news.');
});

it('reads the chosen article with Enter, showing a link to the original', () => {
  panel.open('Terminal');
  news(ARTICLES);

  expect(press('Enter').defaultPrevented).toBe(true);

  expect(send).toHaveBeenLastCalledWith({ type: 'read_news', news_id: 'barrier' });
  expect(link()!.href).toBe('https://example.com/barrier');
  expect(link()!.target).toBe('_blank');
  expect(link()!.rel).toBe('noopener noreferrer');

  news([{ ...ARTICLES[0], read: true }, ARTICLES[1]]);
  expect(items()[0].classList.contains('news-read')).toBe(true);
  expect(link()!.href).toBe('https://example.com/barrier');
});

it('moves through the articles with the arrow keys, and reads one that was read without asking', () => {
  panel.open('Terminal');
  news(ARTICLES);

  press('ArrowDown');
  press('ArrowDown');
  expect(selected()).toBe('Bees in decline');
  press('Enter');
  expect(send).toHaveBeenCalledTimes(1);
  expect(link()!.href).toBe('https://example.com/bees');

  press('ArrowUp');
  press('ArrowUp');
  expect(selected()).toBe('Tidal barrier for the river');
});

it('reads an article that is clicked', () => {
  panel.open('Terminal');
  news(ARTICLES);

  items()[0].querySelector('p')!.click();

  expect(send).toHaveBeenLastCalledWith({ type: 'read_news', news_id: 'barrier' });
});

it('links only to web pages', () => {
  panel.open('Terminal');
  news([{ ...ARTICLES[0], url: 'javascript:alert(1)' }]);

  press('Enter');

  expect(send).toHaveBeenLastCalledWith({ type: 'read_news', news_id: 'barrier' });
  expect(link()).toBeNull();
});

it.each(['Escape', 'e'])('closes with %s, which goes no further', (key) => {
  const reached = vi.fn();
  window.addEventListener('keydown', reached);
  panel.open('Terminal');
  news(ARTICLES);

  press('ArrowDown');
  press(key);

  expect(panel.isOpen).toBe(false);
  expect(section().hidden).toBe(true);
  expect(document.activeElement).toBe(document.body);
  expect(reached).not.toHaveBeenCalled();
  window.removeEventListener('keydown', reached);
});

it('closes with E once per press, not held down or with a modifier', () => {
  panel.open('Terminal');

  press('e', { repeat: true });
  press('e', { metaKey: true });
  press('e', { ctrlKey: true });
  press('e', { altKey: true });
  expect(panel.isOpen).toBe(true);

  press('E', { shiftKey: true });
  expect(panel.isOpen).toBe(false);
});

it('keeps Tab and Shift+Tab inside the panel', () => {
  const reached = vi.fn();
  window.addEventListener('keydown', reached);
  panel.open('Terminal');
  news(ARTICLES);

  expect(press('Tab').defaultPrevented).toBe(true);
  expect(press('Tab', { shiftKey: true }).defaultPrevented).toBe(true);
  expect(document.activeElement).toBe(section());

  press('Enter');
  press('Tab');
  expect(document.activeElement).toBe(link());
  press('Tab');
  expect(document.activeElement).toBe(link());
  expect(press('Tab', { shiftKey: true }).defaultPrevented).toBe(true);
  expect(document.activeElement).toBe(link());

  section().focus();
  press('Tab', { shiftKey: true });
  expect(document.activeElement).toBe(link());
  expect(reached).not.toHaveBeenCalled();
  window.removeEventListener('keydown', reached);
});
