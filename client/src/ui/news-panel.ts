import type { NewsArticle, server } from '../net';
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

/** The news at a terminal: the articles, the one the player is on, and the one they opened. */
export class NewsPanel {
  private readonly panel: HTMLElement;
  private readonly title: HTMLElement;
  private readonly list: HTMLOListElement;
  private readonly status: HTMLElement;
  private readonly server: Server;
  private articles: NewsArticle[] = [];
  private selected?: string;
  private opened?: string;
  readonly stop: () => void;

  constructor(parent: HTMLElement, server: Server) {
    this.server = server;
    this.panel = parent.appendChild(document.createElement('section'));
    this.panel.className = 'news';
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    this.panel.ariaLabel = 'News terminal';
    const header = this.panel.appendChild(document.createElement('header'));
    this.title = header.appendChild(document.createElement('b'));
    header.appendChild(document.createElement('span')).textContent =
      `↑↓ choose · Enter read · Esc or ${NEWS_KEY.toUpperCase()} close`;
    this.status = this.panel.appendChild(document.createElement('p'));
    this.list = this.panel.appendChild(document.createElement('ol'));

    // Keys in the panel mustn't move the player or reach the chat box.
    this.panel.addEventListener('keydown', (event) => {
      event.stopPropagation();
      this.onKey(event);
    });
    this.list.addEventListener('click', (event) => {
      const item = (event.target as Element).closest<HTMLElement>('li[data-id]');
      if (item?.dataset.id) this.read(item.dataset.id);
    });
    this.stop = server.on('news', ({ articles }) => {
      if (this.isOpen) this.show(articles);
    });
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  open(label: string): void {
    this.title.textContent = label;
    this.panel.hidden = false;
    this.panel.focus();
    if (this.server.send({ type: 'list_news' })) {
      this.status.textContent = this.articles.length ? '' : 'Loading the news…';
    } else {
      this.status.textContent = 'Not connected, so there’s no news.';
    }
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
  }

  private onKey(event: KeyboardEvent): void {
    const { key } = event;
    if (key === 'Escape' || pressedNewsKey(event)) {
      event.preventDefault();
      this.close();
    } else if (key === 'Tab') {
      event.preventDefault();
      this.tab(event.shiftKey ? -1 : 1);
    } else if (key === 'ArrowDown' || key === 'ArrowUp') {
      event.preventDefault();
      this.move(key === 'ArrowDown' ? 1 : -1);
    } else if (key === 'Enter' && !(event.target instanceof HTMLAnchorElement)) {
      event.preventDefault();
      if (this.selected) this.read(this.selected);
    }
  }

  private move(step: 1 | -1): void {
    if (this.articles.length === 0) return;
    const at = this.articles.findIndex(({ news_id }) => news_id === this.selected);
    const next = Math.min(Math.max(at + step, 0), this.articles.length - 1);
    this.selected = this.articles[next].news_id;
    this.render();
  }

  private tab(step: 1 | -1): void {
    const stops = [...this.panel.querySelectorAll<HTMLElement>('a[href]')];
    if (stops.length === 0) return;
    const at = stops.indexOf(document.activeElement as HTMLElement);
    const next = at === -1 ? (step === 1 ? 0 : stops.length - 1) : at + step;
    stops[(next + stops.length) % stops.length].focus();
  }

  private read(newsId: string): void {
    const article = this.articles.find(({ news_id }) => news_id === newsId);
    if (!article) return;
    this.selected = this.opened = newsId;
    if (!article.read) this.server.send({ type: 'read_news', news_id: newsId });
    this.render();
  }

  private show(articles: NewsArticle[]): void {
    this.articles = articles;
    const ids = new Set(articles.map(({ news_id }) => news_id));
    if (!this.selected || !ids.has(this.selected)) this.selected = articles[0]?.news_id;
    if (this.opened && !ids.has(this.opened)) this.opened = undefined;
    this.status.textContent = articles.length ? '' : 'No news yet.';
    this.render();
  }

  private render(): void {
    const focused = this.panel.contains(document.activeElement);
    this.list.replaceChildren(...this.articles.map((article) => this.item(article)));
    if (focused && !this.panel.contains(document.activeElement)) this.panel.focus();
    this.list.querySelector('.news-selected')?.scrollIntoView?.({ block: 'nearest' });
  }

  private item(article: NewsArticle): HTMLLIElement {
    const item = document.createElement('li');
    item.dataset.id = article.news_id;
    const open = article.news_id === this.opened;
    item.classList.toggle('news-selected', article.news_id === this.selected);
    item.classList.toggle('news-open', open);
    item.classList.toggle('news-read', article.read);
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
    return item;
  }
}
