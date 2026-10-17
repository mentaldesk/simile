// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi, type MockInstance } from 'vitest';
import { server, type NewsArticle, type WrittenWork } from '../net';
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

const WORKS: WrittenWork[] = [
  {
    work_id: 'river',
    title: 'The river in May',
    artist: { id: 'tobias', name: 'Tobias' },
    form: 'plain verse about the river',
    text: 'The river keeps its counsel,\nbrown and slow.\n\nIt was here before the barrier.',
    statement: 'The council forgets the river was here first.',
    created: '2026-10-17T14:05:00Z',
    read: false,
  },
  {
    work_id: 'bins',
    title: 'Notice to residents',
    artist: { id: 'henrietta', name: 'Henrietta' },
    form: 'stern notices',
    text: 'Bins out by seven.',
    statement: 'Order matters.',
    created: '2026-10-16T09:30:00Z',
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

const tabs = () => [...document.querySelectorAll<HTMLElement>('.news [role="tab"]')];
const shownTab = () => tabs().find((tab) => tab.getAttribute('aria-selected') === 'true')!.textContent;
const byline = (item: HTMLElement) => item.querySelector('small')!.textContent;
const paragraphs = (item: HTMLElement) => [...item.querySelectorAll('p')];

function news(articles: NewsArticle[]): void {
  server.dispatch(JSON.stringify({ type: 'news', articles }));
}

function works(list: WrittenWork[]): void {
  server.dispatch(JSON.stringify({ type: 'works', works: list }));
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

it('switches between the news and the village with the arrow keys or a click', () => {
  panel.open('Terminal');
  news(ARTICLES);
  expect(tabs().map((tab) => tab.textContent)).toEqual(['News', 'Village']);
  expect(shownTab()).toBe('News');

  expect(press('ArrowRight').defaultPrevented).toBe(true);

  expect(shownTab()).toBe('Village');
  expect(send).toHaveBeenLastCalledWith({ type: 'list_works' });
  expect(items()).toEqual([]);

  press('ArrowLeft');
  expect(shownTab()).toBe('News');
  expect(send).toHaveBeenLastCalledWith({ type: 'list_news' });
  expect(titles()).toEqual(['Tidal barrier for the river', 'Bees in decline']);

  tabs()[1].click();
  expect(shownTab()).toBe('Village');
  press('ArrowRight');
  expect(shownTab()).toBe('News');
});

it('lists residents’ writing with its artist, form and when it was made, and the read ones ticked', () => {
  panel.open('Terminal');
  press('ArrowRight');
  works(WORKS);

  expect(status()).toBe('');
  expect(titles()).toEqual(['The river in May', 'Notice to residents']);
  expect(byline(items()[0])).toBe('Tobias · plain verse about the river · 17 Oct, 14:05');
  expect(byline(items()[1])).toBe('Henrietta · stern notices · 16 Oct, 09:30');
  expect(items().map((item) => item.classList.contains('news-read'))).toEqual([false, true]);
  expect(selected()).toBe('The river in May');
  expect(paragraphs(items()[0])).toHaveLength(1);
});

it('opens a work with Enter, sending read_work and showing the artist’s statement', () => {
  panel.open('Terminal');
  press('ArrowRight');
  works(WORKS);

  press('Enter');

  expect(send).toHaveBeenLastCalledWith({ type: 'read_work', work_id: 'river' });
  expect(items()[0].classList.contains('news-open')).toBe(true);
  expect(paragraphs(items()[0]).map((p) => p.textContent)).toEqual([
    'The river keeps its counsel,brown and slow.It was here before the barrier.',
    'The council forgets the river was here first.',
  ]);

  works([{ ...WORKS[0], read: true }, WORKS[1]]);
  expect(items()[0].classList.contains('news-read')).toBe(true);
  expect(items()[0].classList.contains('news-open')).toBe(true);
});

it('opens a work that was read, or clicked, without asking twice', () => {
  panel.open('Terminal');
  press('ArrowRight');
  works(WORKS);
  send.mockClear();

  press('ArrowDown');
  press('Enter');
  expect(send).not.toHaveBeenCalled();
  expect(paragraphs(items()[1])[1].textContent).toBe('Order matters.');

  items()[0].querySelector('b')!.click();
  expect(send).toHaveBeenLastCalledWith({ type: 'read_work', work_id: 'river' });
});

it('keeps a poem’s line breaks', () => {
  panel.open('Terminal');
  press('ArrowRight');
  works(WORKS);

  const poem = paragraphs(items()[0])[0];
  const lines = [...poem.childNodes].map((node) => (node.nodeName === 'BR' ? '\n' : node.textContent));

  expect(lines.join('')).toBe(WORKS[0].text);
  expect(poem.querySelectorAll('br')).toHaveLength(3);
});

it('says when nobody has written anything, or there is no connection, even with no reply', () => {
  panel.open('Terminal');
  press('ArrowRight');
  expect(status()).toBe('Nobody in the village has written anything yet.');

  works([]);
  expect(status()).toBe('Nobody in the village has written anything yet.');

  send.mockReturnValue(false);
  press('ArrowLeft');
  press('ArrowRight');
  expect(status()).toBe('Not connected, so there’s nothing to read.');
});

it('ignores residents’ writing while closed, and opens on the tab it was left on', () => {
  works(WORKS);
  panel.open('Terminal');
  press('ArrowRight');
  expect(items()).toEqual([]);

  panel.close();
  works(WORKS);
  expect(items()).toEqual([]);

  panel.open('Terminal');
  expect(shownTab()).toBe('Village');
  expect(send).toHaveBeenLastCalledWith({ type: 'list_works' });
});

it('keeps each tab’s place while switching between them', () => {
  panel.open('Terminal');
  news(ARTICLES);
  works(WORKS);

  press('ArrowDown');
  press('ArrowRight');
  expect(selected()).toBe('The river in May');
  press('ArrowDown');
  press('Enter');
  press('ArrowLeft');

  expect(selected()).toBe('Bees in decline');
  press('ArrowRight');
  expect(selected()).toBe('Notice to residents');
  expect(items()[1].classList.contains('news-open')).toBe(true);
});

it.each(['Escape', 'e'])('closes with %s from the village, which goes no further', (key) => {
  const reached = vi.fn();
  window.addEventListener('keydown', reached);
  panel.open('Terminal');
  press('ArrowRight');
  works(WORKS);

  press(key);

  expect(panel.isOpen).toBe(false);
  expect(document.activeElement).toBe(document.body);
  expect(reached).not.toHaveBeenCalled();
  window.removeEventListener('keydown', reached);
});

it('keeps Tab inside the panel in the village, and after a tab is clicked', () => {
  const reached = vi.fn();
  window.addEventListener('keydown', reached);
  panel.open('Terminal');
  tabs()[1].click();
  tabs()[1].focus();
  works(WORKS);

  expect(press('Tab').defaultPrevented).toBe(true);
  expect(press('Tab', { shiftKey: true }).defaultPrevented).toBe(true);
  expect(section().contains(document.activeElement)).toBe(true);

  press('Enter');
  expect(send).toHaveBeenLastCalledWith({ type: 'read_work', work_id: 'river' });
  expect(shownTab()).toBe('Village');
  expect(reached).not.toHaveBeenCalled();
  window.removeEventListener('keydown', reached);
});
