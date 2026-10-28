import type { MenuApi, SavedWorld, Worlds } from './api';
import { el, plural } from './dom';
import type { Menu } from './menu';
import { ago } from './news-feeds';

const TODAY = "Today's village";

export const UNSUPERVISED =
  "This server can't switch worlds: it wasn't started with make dev. Stop it and run make dev, which opens the last world played and can open the others from here.";

export function worldDetails(world: SavedWorld, now = Date.now()): string {
  const played = world.played ? `played ${ago(Date.parse(world.played), now)}` : 'never played';
  const day = world.day === null ? 'not started' : `day ${world.day}`;
  return [day, played, world.player, plural(world.residents, 'resident')].join(' · ');
}

function undeletable(world: SavedWorld): string | null {
  if (world.default) return "Today's village is kept: it can't be deleted.";
  if (world.running) return "You're in it: load another world to delete it.";
  return null;
}

/** Every world, to open, rename or delete. */
export class LoadGameScreen {
  private readonly menu: Menu;
  private readonly api: MenuApi;
  private listing: Worlds;
  private readonly list = el('ul', { className: 'menu-worlds' });
  private readonly error = el('p', { className: 'menu-error' });

  constructor(menu: Menu, api: MenuApi, listing: Worlds) {
    this.menu = menu;
    this.api = api;
    this.listing = listing;
    this.error.setAttribute('role', 'alert');
    menu.show(
      el(
        'div',
        { className: 'menu-screen menu-load' },
        el(
          'header',
          {},
          el('h2', {}, 'Load game'),
          menu.button('Back', () => menu.title()),
        ),
        !listing.supervised && el('p', { className: 'menu-note' }, UNSUPERVISED),
        this.list,
        this.error,
      ),
    );
    this.render();
    this.list.querySelector<HTMLElement>('.menu-world-open')?.focus();
  }

  private render(focus?: string): void {
    this.list.replaceChildren(...this.listing.worlds.map((world) => this.row(world)));
    if (focus) this.list.querySelector<HTMLElement>(`[data-id="${focus}"] .menu-world-open`)?.focus();
  }

  private row(world: SavedWorld): HTMLLIElement {
    const refusal = undeletable(world);
    const kept =
      refusal && el('small', { className: 'menu-world-kept', id: `kept-${world.id}` }, refusal);
    const open = el(
      'button',
      {
        type: 'button',
        className: 'menu-world-open menu-nav',
        disabled: !world.running && !this.listing.supervised,
      },
      el(
        'span',
        { className: 'menu-world-name' },
        el('b', {}, world.name),
        world.default &&
          world.name !== TODAY &&
          el('span', { className: 'menu-tag' }, "today's village"),
        world.running && el('span', { className: 'menu-tag menu-tag-running' }, 'playing'),
      ),
      el('small', {}, worldDetails(world)),
      kept,
    );
    open.addEventListener('click', () => void this.menu.load(world));
    const remove = this.menu.button('Delete', () => this.confirm(item, world), 'menu-danger');
    remove.disabled = refusal !== null;
    if (kept) remove.setAttribute('aria-describedby', kept.id);
    const actions = el(
      'div',
      { className: 'menu-world-actions' },
      this.menu.button('Rename', () => this.rename(item, world)),
      remove,
    );
    const item = el('li', { className: 'menu-world' }, open, actions);
    item.dataset.id = world.id;
    return item;
  }

  private rename(item: HTMLLIElement, world: SavedWorld): void {
    const input = el('input', {
      className: 'menu-url',
      value: world.name,
      maxLength: 64,
      spellcheck: false,
      autocomplete: 'off',
    });
    input.setAttribute('aria-label', 'Name');
    const form = el(
      'form',
      { className: 'menu-world-rename' },
      input,
      el('button', { type: 'submit', className: 'menu-primary', textContent: 'Save' }),
      this.menu.button('Cancel', () => this.render(world.id)),
    );
    input.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      this.render(world.id);
    });
    form.addEventListener('submit', (event) => {
      event.preventDefault();
      void this.saveName(world, input.value.trim());
    });
    item.replaceChildren(form);
    input.focus();
    input.select();
  }

  private async saveName(world: SavedWorld, name: string): Promise<void> {
    this.error.textContent = '';
    if (!name || name === world.name) {
      this.render(world.id);
      return;
    }
    try {
      const renamed = await this.api.rename(world.id, name);
      this.listing = {
        ...this.listing,
        worlds: this.listing.worlds.map((w) => (w.id === world.id ? renamed : w)),
      };
      this.render(world.id);
    } catch (error) {
      this.error.textContent = (error as Error).message;
    }
  }

  private confirm(item: HTMLLIElement, world: SavedWorld): void {
    const keep = this.menu.button('Keep it', () => this.render(world.id));
    const confirm = el(
      'div',
      { className: 'menu-world-confirm' },
      el('span', {}, 'Delete ', el('b', {}, world.name), ' for good? It can’t be undone.'),
      el(
        'span',
        { className: 'menu-world-actions' },
        this.menu.button('Delete', () => void this.remove(world), 'menu-danger'),
        keep,
      ),
    );
    confirm.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      event.stopPropagation();
      this.render(world.id);
    });
    item.replaceChildren(confirm);
    keep.focus();
  }

  private async remove(world: SavedWorld): Promise<void> {
    this.error.textContent = '';
    try {
      await this.api.remove(world.id);
      const at = this.listing.worlds.indexOf(world);
      const worlds = this.listing.worlds.filter((w) => w.id !== world.id);
      this.listing = { ...this.listing, worlds };
      this.render(worlds[Math.min(at, worlds.length - 1)]?.id);
    } catch (error) {
      this.error.textContent = (error as Error).message;
      this.render(world.id);
    }
  }
}
