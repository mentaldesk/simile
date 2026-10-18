import type { CheckedFeed, MenuApi, NewsFeed, NewsFeeds } from './api';
import { el, plural } from './dom';
import type { Menu } from './menu';

const PLACEHOLDER = 'https://example.com/feed.xml';

/** How long before `now` the time `then` was, both in milliseconds. */
export function ago(then: number, now = Date.now()): string {
  const minutes = Math.floor(Math.max(0, now - then) / 60_000);
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${plural(hours, 'hour')} ago`;
  const days = Math.floor(hours / 24);
  if (days < 30) return `${plural(days, 'day')} ago`;
  return `on ${new Date(then).toISOString().slice(0, 10)}`;
}

export function usageNote({ feeds, calls_per_feed: calls, max }: NewsFeeds): string {
  const on = feeds.filter((feed) => feed.on).length;
  const total = on ? `, so up to ${on * calls} at once with ${on} on` : '';
  return (
    `Each feed that's on adds up to ${calls} Haiku calls when its new stories are analysed` +
    `${total}. The list takes at most ${max}.`
  );
}

export class NewsFeedsScreen {
  private readonly menu: Menu;
  private readonly api: MenuApi;
  private listing: NewsFeeds;
  private checked: CheckedFeed | null = null;
  private busy = false;
  private readonly notes = el('div', { className: 'menu-notes' });
  private readonly list = el('ul', { className: 'menu-feeds' });
  private readonly usage = el('p', { className: 'menu-hint menu-usage' });
  private readonly url = el('input', {
    type: 'url',
    className: 'menu-url',
    placeholder: PLACEHOLDER,
    spellcheck: false,
    autocomplete: 'off',
  });
  private readonly check: HTMLButtonElement;
  private readonly preview = el('div', { className: 'menu-preview', hidden: true });
  private readonly error = el('p', { className: 'menu-error' });
  private readonly reset: HTMLButtonElement;
  private readonly count = el('span', { className: 'menu-hint' });

  constructor(menu: Menu, api: MenuApi, listing: NewsFeeds) {
    this.menu = menu;
    this.api = api;
    this.listing = listing;
    this.url.setAttribute('aria-label', 'Feed URL');
    this.error.setAttribute('role', 'alert');
    this.check = el('button', { type: 'submit', textContent: 'Check' });
    this.reset = menu.button('Reset to defaults', () => this.resetClicked());
    this.reset.addEventListener('blur', () => this.renderReset());
    const form = el('form', { className: 'menu-add', noValidate: true }, this.url, this.check);
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      void this.checkFeed();
    });
    this.url.addEventListener('input', () => {
      this.error.textContent = '';
      this.forget();
    });

    menu.show(
      el(
        'div',
        { className: 'menu-screen menu-news' },
        el(
          'header',
          {},
          el('h2', {}, 'News feeds'),
          menu.button('Back', () => menu.title()),
        ),
        el(
          'p',
          { className: 'menu-intro' },
          'What the village reads at the terminals, in every world on this computer. ' +
            'Changes apply at the next refresh.',
        ),
        this.notes,
        this.list,
        this.usage,
        el('h3', {}, 'Add a feed ', el('small', {}, 'paste the URL of an RSS or Atom feed')),
        form,
        this.preview,
        this.error,
        el('footer', {}, this.reset, this.count),
      ),
    );
    this.render();
  }

  private render(): void {
    const { feeds, max, override, fetching } = this.listing;
    const notes = [
      override &&
        el(
          'p',
          { className: 'menu-note' },
          'This run reads ',
          el('code', {}, 'SIMILE_NEWS_FEED'),
          `'s ${plural(override.length, 'feed')} instead. Changes here apply once it's unset.`,
        ),
      !fetching &&
        el(
          'p',
          { className: 'menu-note' },
          'News is off for this run (',
          el('code', {}, 'SIMILE_NEWS=0'),
          '), so nothing is fetched.',
        ),
    ];
    this.notes.replaceChildren(...notes.filter((note): note is HTMLParagraphElement => !!note));
    this.list.replaceChildren(...feeds.map((feed) => this.row(feed)));
    if (!feeds.length) {
      this.list.append(
        el('li', { className: 'menu-hint' }, 'No feeds. The terminals keep the stories they have.'),
      );
    }
    this.usage.textContent = usageNote(this.listing);

    const full = feeds.length >= max;
    this.url.disabled = this.check.disabled = full || this.busy;
    this.url.placeholder = full ? 'The list is full. Remove a feed to add another.' : PLACEHOLDER;
    const on = feeds.filter((feed) => feed.on).length;
    this.count.textContent = `${plural(feeds.length, 'feed')} of ${max}, ${on} on`;
    this.renderReset();
    this.renderPreview();
  }

  private row(feed: NewsFeed): HTMLLIElement {
    const name = feed.name || feed.url;
    const toggle = el('button', { type: 'button', className: 'menu-switch' });
    toggle.setAttribute('role', 'switch');
    toggle.setAttribute('aria-checked', String(feed.on));
    toggle.setAttribute('aria-label', `Read ${name}`);
    toggle.dataset.focus = `switch ${feed.url}`;
    toggle.addEventListener('click', () => {
      void this.act(() => this.api.switchFeed(feed.url, !feed.on));
    });
    const remove = this.menu.button(
      'Remove',
      () => void this.act(() => this.api.removeFeed(feed.url)),
      'menu-remove',
    );
    remove.setAttribute('aria-label', `Remove ${name}`);
    const fetched =
      feed.checked === null ? 'not fetched yet' : `fetched ${ago(feed.checked * 1000)}`;
    const row = el(
      'li',
      { className: 'menu-feed' },
      toggle,
      el(
        'div',
        { className: 'menu-feed-text' },
        el('b', {}, name),
        el('span', { className: 'menu-feed-url' }, feed.url),
      ),
      el('span', { className: 'menu-feed-checked' }, fetched),
      remove,
    );
    row.dataset.on = String(feed.on);
    return row;
  }

  private renderPreview(): void {
    const found = this.checked;
    this.preview.hidden = !found;
    if (!found) {
      this.preview.replaceChildren();
      return;
    }
    const latest = found.latest
      ? `Latest: “${found.latest.title}”, ${ago(Date.parse(found.latest.published))}`
      : 'No stories in it yet.';
    this.preview.replaceChildren(
      el(
        'div',
        { className: 'menu-feed-text' },
        el('b', {}, found.title || found.url),
        el('span', { className: 'menu-feed-url' }, found.url),
        el('span', { className: 'menu-latest' }, latest),
      ),
      el(
        'div',
        { className: 'menu-preview-actions' },
        this.menu.button('Cancel', () => this.forget()),
        this.menu.button('Add', () => void this.add(found.url), 'menu-primary'),
      ),
    );
  }

  private renderReset(): void {
    this.reset.textContent = 'Reset to defaults';
    this.reset.classList.remove('menu-danger');
    this.reset.disabled = this.listing.defaults;
  }

  private resetClicked(): void {
    if (!this.reset.classList.contains('menu-danger')) {
      this.reset.textContent = 'Really reset?';
      this.reset.classList.add('menu-danger');
      return;
    }
    void this.act(() => this.api.resetFeeds());
  }

  private async checkFeed(): Promise<void> {
    const url = this.url.value.trim();
    if (!url || this.busy) return;
    this.checked = null;
    this.check.textContent = 'Checking…';
    await this.act(async () => {
      this.checked = await this.api.checkFeed(url);
      return this.listing;
    });
    this.check.textContent = 'Check';
  }

  private async add(url: string): Promise<void> {
    await this.act(async () => {
      const listing = await this.api.addFeed(url);
      this.checked = null;
      this.url.value = '';
      return listing;
    });
    if (!this.checked) this.url.focus();
  }

  private forget(): void {
    if (!this.checked) return;
    this.checked = null;
    this.renderPreview();
  }

  private async act(change: () => Promise<NewsFeeds>): Promise<void> {
    if (this.busy) return;
    const focus = (document.activeElement as HTMLElement | null)?.dataset?.focus;
    this.busy = true;
    this.error.textContent = '';
    this.render();
    try {
      this.listing = await change();
    } catch (error) {
      this.error.textContent = (error as Error).message;
    } finally {
      this.busy = false;
      this.render();
      if (focus) {
        [...this.list.querySelectorAll<HTMLElement>('[data-focus]')]
          .find((control) => control.dataset.focus === focus)
          ?.focus();
      }
    }
  }
}
