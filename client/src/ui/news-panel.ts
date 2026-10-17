import type { ClientMessage, NewsArticle, WrittenWork, server } from '../net';
import { pressedNewsKey } from './keys';
import { NEWS_KEY } from './tuning';

type Server = Pick<typeof server, 'on' | 'send'>;

/** Only web links: a feed could carry a `javascript:` one. */
function webLink(url: string): string | undefined {
  try {
    return ['http:', 'https:'].includes(new URL(url).protocol) ? url : undefined;
  } catch {
    return undefined;
  }
}

/** Sim time is in UTC, so its wall clock is UTC's. */
const MADE = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'UTC',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

function madeAt(created: string): string {
  const time = new Date(created);
  return Number.isNaN(time.getTime()) ? created : MADE.format(time);
}

function appendLines(parent: HTMLElement, text: string): void {
  text.split(/\r?\n/).forEach((line, i) => {
    if (i > 0) parent.appendChild(document.createElement('br'));
    parent.append(line);
  });
}

type Kind<T> = {
  label: string;
  list: ClientMessage;
  read: (id: string) => ClientMessage;
  id: (entry: T) => string;
  fill: (item: HTMLLIElement, entry: T, open: boolean) => void;
  loading?: string;
  empty: string;
  offline: string;
};

const NEWS: Kind<NewsArticle> = {
  label: 'News',
  list: { type: 'list_news' },
  read: (news_id) => ({ type: 'read_news', news_id }),
  id: ({ news_id }) => news_id,
  loading: 'Loading the news…',
  empty: 'No news yet.',
  offline: 'Not connected, so there’s no news.',
  fill(item, article, open) {
    item.appendChild(document.createElement('b')).textContent = article.title;
    if (article.source) {
      item.appendChild(document.createElement('small')).textContent = article.source;
    }
    item.appendChild(document.createElement('p')).textContent = article.summary;
    const url = webLink(article.url);
    if (open && url) {
      const link = item.appendChild(document.createElement('a'));
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      link.textContent = 'Read the original ↗';
    }
  },
};

// No loading message: a server without the works module never answers.
const VILLAGE: Kind<WrittenWork> = {
  label: 'Village',
  list: { type: 'list_works' },
  read: (work_id) => ({ type: 'read_work', work_id }),
  id: ({ work_id }) => work_id,
  empty: 'Nobody in the village has written anything yet.',
  offline: 'Not connected, so there’s nothing to read.',
  fill(item, work, open) {
    item.appendChild(document.createElement('b')).textContent = work.title;
    item.appendChild(document.createElement('small')).textContent =
      `${work.artist.name} · ${work.form} · ${madeAt(work.created)}`;
    appendLines(item.appendChild(document.createElement('p')), work.text);
    if (open && work.statement) {
      const statement = item.appendChild(document.createElement('p'));
      statement.appendChild(document.createElement('i')).textContent = work.statement;
    }
  },
};

/** A tab's entries, the one the player is on, and the one they opened. */
class Shelf<T extends { read: boolean }> {
  readonly kind: Kind<T>;
  status = '';
  private readonly server: Server;
  private entries: T[] = [];
  private selected?: string;
  private opened?: string;

  constructor(kind: Kind<T>, server: Server) {
    this.kind = kind;
    this.server = server;
  }

  request(): void {
    if (this.server.send(this.kind.list)) {
      this.status = this.entries.length ? '' : (this.kind.loading ?? this.kind.empty);
    } else {
      this.status = this.kind.offline;
    }
  }

  show(entries: T[]): void {
    this.entries = entries;
    const ids = new Set(entries.map(this.kind.id));
    if (!this.selected || !ids.has(this.selected)) {
      this.selected = entries.length ? this.kind.id(entries[0]) : undefined;
    }
    if (this.opened && !ids.has(this.opened)) this.opened = undefined;
    this.status = entries.length ? '' : this.kind.empty;
  }

  move(step: 1 | -1): void {
    if (this.entries.length === 0) return;
    const at = this.entries.findIndex((entry) => this.kind.id(entry) === this.selected);
    const next = Math.min(Math.max(at + step, 0), this.entries.length - 1);
    this.selected = this.kind.id(this.entries[next]);
  }

  read(id = this.selected): boolean {
    const entry = this.entries.find((each) => this.kind.id(each) === id);
    if (!id || !entry) return false;
    this.selected = this.opened = id;
    if (!entry.read) this.server.send(this.kind.read(id));
    return true;
  }

  items(): HTMLLIElement[] {
    return this.entries.map((entry) => {
      const id = this.kind.id(entry);
      const item = document.createElement('li');
      item.dataset.id = id;
      item.classList.toggle('news-selected', id === this.selected);
      item.classList.toggle('news-open', id === this.opened);
      item.classList.toggle('news-read', entry.read);
      this.kind.fill(item, entry, id === this.opened);
      return item;
    });
  }
}

/** A terminal's tabs: the news, and residents' writing. */
export class NewsPanel {
  private readonly panel: HTMLElement;
  private readonly title: HTMLElement;
  private readonly tabs: HTMLButtonElement[];
  private readonly list: HTMLOListElement;
  private readonly status: HTMLElement;
  private readonly news: Shelf<NewsArticle>;
  private readonly works: Shelf<WrittenWork>;
  private shown = 0;
  readonly stop: () => void;

  constructor(parent: HTMLElement, server: Server) {
    this.news = new Shelf(NEWS, server);
    this.works = new Shelf(VILLAGE, server);
    this.panel = parent.appendChild(document.createElement('section'));
    this.panel.className = 'news';
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    this.panel.ariaLabel = 'News terminal';
    const header = this.panel.appendChild(document.createElement('header'));
    this.title = header.appendChild(document.createElement('b'));
    header.appendChild(document.createElement('span')).textContent =
      `←→ switch · ↑↓ choose · Enter read · Esc or ${NEWS_KEY.toUpperCase()} close`;
    const tablist = this.panel.appendChild(document.createElement('div'));
    tablist.className = 'news-tabs';
    tablist.setAttribute('role', 'tablist');
    this.tabs = this.shelves.map((shelf, i) => {
      const tab = tablist.appendChild(document.createElement('button'));
      tab.type = 'button';
      tab.tabIndex = -1;
      tab.setAttribute('role', 'tab');
      tab.textContent = shelf.kind.label;
      tab.addEventListener('click', () => this.showTab(i));
      return tab;
    });
    this.status = this.panel.appendChild(document.createElement('p'));
    this.list = this.panel.appendChild(document.createElement('ol'));
    this.markTab();

    // Keys in the panel mustn't move the player or reach the chat box.
    this.panel.addEventListener('keydown', (event) => {
      event.stopPropagation();
      this.onKey(event);
    });
    this.list.addEventListener('click', (event) => {
      const item = (event.target as Element).closest<HTMLElement>('li[data-id]');
      if (item?.dataset.id && this.shelf.read(item.dataset.id)) this.render();
    });
    const stopNews = server.on('news', ({ articles }) => this.receive(this.news, articles));
    const stopWorks = server.on('works', ({ works }) => this.receive(this.works, works));
    this.stop = () => {
      stopNews();
      stopWorks();
    };
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  open(label: string): void {
    this.title.textContent = label;
    this.panel.hidden = false;
    this.panel.focus();
    this.shelf.request();
    this.render();
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  private get shelves(): [Shelf<NewsArticle>, Shelf<WrittenWork>] {
    return [this.news, this.works];
  }

  private get shelf(): Shelf<NewsArticle> | Shelf<WrittenWork> {
    return this.shelves[this.shown];
  }

  private receive<T extends { read: boolean }>(shelf: Shelf<T>, entries: T[]): void {
    if (!this.isOpen) return;
    shelf.show(entries);
    this.render();
  }

  private onKey(event: KeyboardEvent): void {
    const { key } = event;
    if (key === 'Escape' || pressedNewsKey(event)) {
      event.preventDefault();
      this.close();
    } else if (key === 'Tab') {
      event.preventDefault();
      this.tab(event.shiftKey ? -1 : 1);
    } else if (key === 'ArrowLeft' || key === 'ArrowRight') {
      event.preventDefault();
      const count = this.tabs.length;
      this.showTab((this.shown + (key === 'ArrowRight' ? 1 : -1) + count) % count);
    } else if (key === 'ArrowDown' || key === 'ArrowUp') {
      event.preventDefault();
      this.shelf.move(key === 'ArrowDown' ? 1 : -1);
      this.render();
    } else if (key === 'Enter' && !(event.target instanceof HTMLAnchorElement)) {
      event.preventDefault();
      if (this.shelf.read()) this.render();
    }
  }

  private showTab(index: number): void {
    if (index === this.shown) return;
    this.shown = index;
    this.markTab();
    this.list.scrollTop = 0;
    this.shelf.request();
    this.render();
  }

  private markTab(): void {
    this.tabs.forEach((tab, i) => tab.setAttribute('aria-selected', String(i === this.shown)));
  }

  private tab(step: 1 | -1): void {
    const stops = [...this.panel.querySelectorAll<HTMLElement>('a[href]')];
    if (stops.length === 0) return;
    const at = stops.indexOf(document.activeElement as HTMLElement);
    const next = at === -1 ? (step === 1 ? 0 : stops.length - 1) : at + step;
    stops[(next + stops.length) % stops.length].focus();
  }

  private render(): void {
    const focused = this.panel.contains(document.activeElement);
    this.status.textContent = this.shelf.status;
    this.list.replaceChildren(...this.shelf.items());
    if (focused && !this.panel.contains(document.activeElement)) this.panel.focus();
    this.list.querySelector('.news-selected')?.scrollIntoView?.({ block: 'nearest' });
  }
}
