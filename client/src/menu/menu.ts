import type {
  LibraryCharacter,
  MadeWorld,
  MenuApi,
  Missing,
  Pin,
  Resident,
  SavedWorld,
  Worlds,
} from './api';
import { type Child, el, plural } from './dom';
import { LoadGameScreen } from './load-game';
import './menu.css';
import { suggestName } from './names';
import { BONDS, bondLabel, NewWorldState } from './new-world';
import { NewsFeedsScreen } from './news-feeds';

/** A screen saying what's happening while a world is made or opened. */
export class Progress {
  readonly screen: HTMLElement;
  private readonly heading = el('h2');
  private readonly status = el('p', { className: 'menu-progress-status' });

  constructor(heading: string, status: string) {
    this.status.setAttribute('role', 'status');
    this.screen = el(
      'div',
      { className: 'menu-screen menu-progress' },
      this.heading,
      el('div', { className: 'menu-progress-bar' }, el('span')),
      this.status,
    );
    this.say(heading, status);
  }

  say(heading: string, status: string): void {
    this.heading.textContent = heading;
    this.status.textContent = status;
  }
}

export type MenuActions = {
  /** Plays the world the server is running. */
  play(): void;
  /** Reloads the page into the game, once the server runs another world. */
  enter(): void;
  creator?: () => void;
};

export type MenuTiming = { pollMs: number; patienceMs: number };

const TIMING: MenuTiming = { pollMs: 500, patienceMs: 60_000 };

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

function continueHint({ current, worlds }: Worlds): string {
  const day = worlds.find((world) => world.id === current.id && current.id !== null)?.day;
  const parts = [current.id === null ? `World ${current.name}` : current.name];
  if (day) parts.push(`day ${day}`);
  parts.push(plural(current.residents.length, 'resident'));
  return parts.join(' · ');
}

export class Menu {
  readonly root: HTMLElement;
  private readonly api: MenuApi;
  private readonly actions: MenuActions;
  private readonly timing: MenuTiming;
  private back: (() => void) | null = null;

  constructor(
    parent: HTMLElement,
    api: MenuApi,
    actions: MenuActions,
    timing: Partial<MenuTiming> = {},
  ) {
    this.api = api;
    this.actions = actions;
    this.timing = { ...TIMING, ...timing };
    this.root = parent.appendChild(el('div', { className: 'menu', tabIndex: -1 }));
    this.root.addEventListener('keydown', (event) => this.key(event));
    this.title();
  }

  remove(): void {
    this.root.remove();
  }

  title(): void {
    const hint = el('small', {}, 'Asking the server…');
    const saved = el('small', {}, 'Open, rename or delete a world');
    const characters = this.actions.creator;
    const items = [
      this.item('Continue', hint, () => this.actions.play()),
      this.item('New game', el('small', {}, 'Make a new world and start it'), () =>
        this.newGame(),
      ),
      this.item('Load game', saved, () => void this.loadGame()),
      this.item(
        'Characters',
        el(
          'small',
          {},
          characters ? 'Browse and make characters' : 'Coming with the character creator',
        ),
        () => characters?.(),
        !characters,
      ),
      this.item('News feeds', el('small', {}, 'Choose what the village reads'), () =>
        this.newsFeeds(),
      ),
    ];
    this.show(
      el(
        'div',
        { className: 'menu-screen menu-title' },
        el('h1', {}, 'Simile'),
        el('nav', {}, ...items),
      ),
      null,
    );
    items[0].focus();
    this.api.worlds().then(
      (listing) => {
        hint.textContent = continueHint(listing);
        saved.textContent = `${plural(listing.worlds.length, 'world')} to open, rename or delete`;
      },
      () => (hint.textContent = "The server isn't answering yet"),
    );
  }

  async newGame(): Promise<void> {
    this.show(el('div', { className: 'menu-screen' }, el('p', {}, 'Opening the library…')));
    try {
      const [listing, characters] = await Promise.all([this.api.worlds(), this.api.characters()]);
      const name = suggestName(listing.worlds.map((world) => world.name));
      new NewWorldScreen(this, this.api, new NewWorldState(listing.houses), characters, name);
    } catch (error) {
      this.failed(`Couldn't open the library: ${(error as Error).message}`);
    }
  }

  async loadGame(): Promise<void> {
    this.show(el('div', { className: 'menu-screen' }, el('p', {}, 'Asking the server…')));
    try {
      new LoadGameScreen(this, this.api, await this.api.worlds());
    } catch (error) {
      this.failed(`Couldn't list the worlds: ${(error as Error).message}`);
    }
  }

  async newsFeeds(): Promise<void> {
    this.show(el('div', { className: 'menu-screen' }, el('p', {}, 'Asking the server…')));
    try {
      new NewsFeedsScreen(this, this.api, await this.api.feeds());
    } catch (error) {
      this.failed(`Couldn't list the feeds: ${(error as Error).message}`);
    }
  }

  /** Opens a saved world: switches the server to it, then reloads into it. */
  async load(world: SavedWorld): Promise<void> {
    if (world.running) {
      this.actions.play();
      return;
    }
    const progress = this.progress(`Opening ${world.name}`, 'Saving the world you were in…');
    try {
      const { opening } = await this.api.open(world.id);
      if (opening) await this.arrive(world.id, world.name, progress);
      else this.actions.enter();
    } catch (error) {
      this.failed(`Couldn't open ${world.name}: ${(error as Error).message}`, () =>
        void this.loadGame(),
      );
    }
  }

  /** Waits for the server to come back on world `id`, then reloads into it. */
  async arrive(id: string, name: string, progress: Progress): Promise<void> {
    progress.say(`Opening ${name}`, 'Saving the world you were in…');
    const { pollMs, patienceMs } = this.timing;
    for (const until = Date.now() + patienceMs; Date.now() <= until; ) {
      await sleep(pollMs);
      const listing = await this.api.worlds().catch(() => null);
      if (listing?.current.id === id) {
        progress.say(`Opening ${name}`, 'Ready.');
        this.actions.enter();
        return;
      }
      if (!listing) progress.say(`Opening ${name}`, `Starting ${name}…`);
    }
    throw new Error(`the server didn't come back within ${patienceMs / 1000} s`);
  }

  progress(heading: string, status: string): Progress {
    const progress = new Progress(heading, status);
    this.show(progress.screen, null);
    return progress;
  }

  failed(reason: string, back = () => this.title()): void {
    this.show(
      el(
        'div',
        { className: 'menu-screen' },
        el('p', { className: 'menu-error' }, reason),
        el('footer', {}, this.button('Back', back)),
      ),
      back,
    );
  }
  ready(world: MadeWorld, names: Map<string, string>): void {
    const name = (id: string) => names.get(id) ?? id;
    const copy = this.button('Copy', () => {
      void navigator.clipboard
        ?.writeText(world.restart.command)
        .then(() => (copy.textContent = 'Copied'));
    });
    const where = world.data.startsWith('/') ? world.data : `server/${world.data}`;
    this.show(
      el(
        'div',
        { className: 'menu-screen menu-ready' },
        el('h2', {}, 'Your new world is ready'),
        el('p', {}, 'World ', el('b', {}, world.name), `, in ${where}. Its residents:`),
        el('ul', { className: 'menu-list' }, ...world.residents.map(residentLine)),
        world.bonds.length > 0 && el('h3', {}, 'Bonds'),
        world.bonds.length > 0 &&
          el(
            'ul',
            { className: 'menu-list' },
            ...world.bonds.map((bond) => el('li', {}, pinLine(bond, name))),
          ),
        ...missingLines(world.missing),
        el('h3', {}, 'Start it'),
        el(
          'p',
          {},
          "This server can't switch worlds, because ",
          el('code', {}, 'make dev'),
          " didn't start it. Stop it and start it again from the repo root with:",
        ),
        el('div', { className: 'menu-command' }, el('code', {}, world.restart.command), copy),
        el(
          'p',
          { className: 'menu-hint' },
          'Or start a plain ',
          el('code', {}, 'make dev'),
          ', which opens the last world played and switches worlds from the menu.',
        ),
        el(
          'footer',
          {},
          this.button('Back to the menu', () => this.title()),
        ),
      ),
    );
  }

  /** Shows `screen`, which Esc leaves by `back`: the title, unless it's null. */
  show(screen: HTMLElement, back: (() => void) | null = () => this.title()): void {
    this.back = back;
    this.root.replaceChildren(screen);
    this.root.scrollTop = 0;
    if (!screen.contains(document.activeElement)) this.root.focus();
  }

  button(label: string, onClick: () => void, className = ''): HTMLButtonElement {
    const button = el('button', { type: 'button', className, textContent: label });
    button.addEventListener('click', onClick);
    return button;
  }

  private key(event: KeyboardEvent): void {
    if (event.key === 'Escape' && this.back) {
      event.preventDefault();
      this.back();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      const stops = [...this.root.querySelectorAll<HTMLElement>('.menu-nav:not(:disabled)')];
      const at = stops.indexOf(document.activeElement as HTMLElement);
      if (at === -1 && document.activeElement !== this.root) return;
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      stops[(at + step + stops.length) % stops.length]?.focus();
    }
  }

  private item(
    label: string,
    hint: HTMLElement,
    onClick: () => void,
    disabled = false,
  ): HTMLButtonElement {
    const button = el(
      'button',
      { type: 'button', className: 'menu-item menu-nav', disabled },
      label,
      hint,
    );
    button.addEventListener('click', onClick);
    return button;
  }
}

class NewWorldScreen {
  private readonly menu: Menu;
  private readonly api: MenuApi;
  private readonly state: NewWorldState;
  private readonly names: Map<string, string>;
  private readonly cards = new Map<string, HTMLButtonElement>();
  private readonly count = el('output', { className: 'menu-count-value' });
  private readonly less: HTMLButtonElement;
  private readonly more: HTMLButtonElement;
  private readonly summary = el('p', { className: 'menu-summary' });
  private readonly randomise: HTMLButtonElement;
  private readonly start: HTMLButtonElement;
  private readonly actor = el('select');
  private readonly kind = el('select');
  private readonly target = el('select');
  private readonly pinForm: HTMLElement;
  private readonly pinHint = el(
    'p',
    { className: 'menu-hint' },
    'Pick two residents to pin a bond between them.',
  );
  private readonly pins = el('ul', { className: 'menu-list menu-pins' });
  private readonly error = el('p', { className: 'menu-error' });
  private readonly name = el('input', {
    className: 'menu-url menu-name-input',
    maxLength: 64,
    spellcheck: false,
    autocomplete: 'off',
  });
  private readonly screen: HTMLElement;

  constructor(
    menu: Menu,
    api: MenuApi,
    state: NewWorldState,
    characters: LibraryCharacter[],
    name: string,
  ) {
    this.menu = menu;
    this.api = api;
    this.state = state;
    this.names = new Map(characters.map(({ id, name }) => [id, name]));
    this.less = menu.button(
      '−',
      () => this.change(() => state.setCount(state.count - 1)),
      'menu-step',
    );
    this.more = menu.button(
      '+',
      () => this.change(() => state.setCount(state.count + 1)),
      'menu-step',
    );
    this.less.setAttribute('aria-label', 'Fewer residents');
    this.more.setAttribute('aria-label', 'More residents');
    this.actor.setAttribute('aria-label', 'Who');
    this.kind.setAttribute('aria-label', 'Bond');
    this.target.setAttribute('aria-label', 'With whom');
    this.error.setAttribute('role', 'alert');
    this.randomise = menu.button('Randomise', () => void this.draw());
    this.start = el('button', { type: 'submit', className: 'menu-primary', textContent: 'Start' });
    this.name.value = name;
    this.name.setAttribute('aria-label', 'Name');
    const naming = el(
      'form',
      { className: 'menu-name' },
      el('label', {}, el('span', {}, 'Name'), this.name),
      this.start,
    );
    naming.addEventListener('submit', (event) => {
      event.preventDefault();
      void this.create();
    });
    for (const { kind, label } of BONDS)
      this.kind.append(el('option', { value: kind, textContent: label }));
    this.pinForm = el(
      'div',
      { className: 'menu-pin-form' },
      this.actor,
      this.kind,
      this.target,
      menu.button('Pin', () => this.pin()),
    );

    const year = new Date().getFullYear();
    const grid = el('ul', { className: 'menu-cards' });
    for (const character of characters) {
      const card = el(
        'button',
        { type: 'button', className: 'menu-card', title: character.persona },
        el('b', {}, character.name),
        el('span', {}, `${year - character.birth_year} · ${character.occupation}`),
        el('span', { className: 'menu-origin' }, character.origin),
        character.source === 'player' &&
          el('span', { className: 'menu-badge menu-yours' }, 'yours'),
        el('span', { className: 'menu-badge menu-state' }),
      );
      card.addEventListener('click', () => this.toggle(character.id));
      this.cards.set(character.id, card);
      grid.append(el('li', {}, card));
    }

    this.screen = el(
      'div',
      { className: 'menu-screen menu-new' },
      el(
        'header',
        {},
        el('h2', {}, 'New game'),
        menu.button('Back', () => menu.title()),
      ),
      naming,
      el(
        'p',
        { className: 'menu-hint' },
        'Start now for a village drawn at random, or choose who lives there first.',
      ),
      this.error,
      el(
          'div',
          { className: 'menu-count' },
          el('span', {}, 'Residents'),
          this.less,
          this.count,
          this.more,
          el('span', { className: 'menu-hint' }, `of ${plural(state.houses, 'house')}`),
          el('span', { className: 'menu-spacer' }),
          this.randomise,
          menu.button('Clear', () => this.change(() => state.clear())),
        ),
        this.summary,
        grid,
        el('h3', {}, 'Bonds ', el('small', {}, 'optional: pin a tie between two residents')),
        this.pinHint,
        this.pinForm,
        this.pins,
        el(
          'footer',
          {},
          el(
            'span',
            { className: 'menu-hint' },
            "Today's village is kept. A new world gets a folder of its own.",
          ),
        ),
    );
    menu.show(this.screen);
    this.start.focus({ preventScroll: true });
    this.update();
  }

  private toggle(id: string): void {
    this.change(() => {
      if (!this.state.toggle(id))
        this.error.textContent = `All ${this.state.houses} houses are taken.`;
    });
  }

  private change(action: () => void): void {
    this.error.textContent = '';
    action();
    this.update();
  }

  private async draw(): Promise<void> {
    await this.busy(async () =>
      this.state.randomised(await this.api.draw(this.state.drawRequest())),
    );
  }

  private async create(): Promise<void> {
    const name = this.name.value.trim() || undefined;
    const progress = this.menu.progress(
      `Making ${name ?? 'a new world'}`,
      'Casting the residents…',
    );
    let made: MadeWorld;
    try {
      made = await this.api.create({ ...this.state.request(), name, open: true });
    } catch (error) {
      this.menu.show(this.screen);
      this.error.textContent = (error as Error).message;
      this.start.focus({ preventScroll: true });
      return;
    }
    if (!made.opening) {
      this.menu.ready(made, this.names);
      return;
    }
    try {
      await this.menu.arrive(made.id, made.name, progress);
    } catch (error) {
      this.menu.failed(`Couldn't open ${made.name}: ${(error as Error).message}`);
    }
  }

  private async busy(work: () => Promise<void>): Promise<void> {
    this.error.textContent = '';
    this.randomise.disabled = this.start.disabled = true;
    try {
      await work();
    } catch (error) {
      this.error.textContent = (error as Error).message;
    } finally {
      this.randomise.disabled = this.start.disabled = false;
      this.update();
    }
  }

  private pin(): void {
    this.change(() => {
      const pin = {
        actor: this.actor.value,
        kind: this.kind.value,
        target: this.target.value,
      } as Pin;
      const refused = this.state.pin(pin);
      if (refused) this.error.textContent = refused;
    });
  }

  private update(): void {
    const { state } = this;
    for (const [id, card] of this.cards) {
      const how = state.isPicked(id) ? 'picked' : state.isDrawn(id) ? 'drawn' : '';
      card.setAttribute('aria-pressed', String(how !== ''));
      card.dataset.state = how;
      card.querySelector('.menu-state')!.textContent = how;
    }
    this.count.textContent = String(state.count);
    this.less.disabled = state.count <= Math.max(1, state.picks.length);
    this.more.disabled = state.count >= state.houses;
    this.summary.textContent = summaryOf(state);

    const residents = state.residents;
    this.pinForm.hidden = residents.length < 2;
    this.pinHint.hidden = !this.pinForm.hidden;
    for (const select of [this.actor, this.target]) {
      const chosen = select.value;
      select.replaceChildren(
        ...residents.map((id) =>
          el('option', { value: id, textContent: this.names.get(id) ?? id }),
        ),
      );
      if (residents.includes(chosen)) select.value = chosen;
    }
    if (this.target.value === this.actor.value && residents.length > 1) {
      this.target.value = residents.find((id) => id !== this.actor.value)!;
    }
    const name = (id: string) => this.names.get(id) ?? id;
    this.pins.replaceChildren(
      ...state.pins.map((pin, i) =>
        el(
          'li',
          {},
          pinLine(pin, name),
          ' ',
          this.menu.button('×', () => this.change(() => state.unpin(i)), 'menu-unpin'),
        ),
      ),
    );
  }
}

function summaryOf(state: NewWorldState): string {
  const parts = [`${state.picks.length} picked`];
  if (state.draws.length) parts.push(`${state.draws.length} drawn`);
  if (state.open) parts.push(`${state.open} more drawn at random when it starts`);
  return `${parts.join(', ')}.`;
}

function pinLine(pin: Pin, name: (id: string) => string): string {
  return `${name(pin.actor)} ${bondLabel(pin.kind)} ${name(pin.target)}`;
}

function residentLine({ name, age, occupation, home }: Resident): HTMLLIElement {
  return el(
    'li',
    {},
    el('b', {}, name),
    `, ${age}, ${occupation}`,
    el('span', { className: 'menu-hint' }, ` · ${home.replace('_', ' ')}`),
  );
}

function missingLines(missing: Missing[]): Child[] {
  const needing = (need: Missing['needs'][number]) =>
    missing.filter((m) => m.needs.includes(need)).map((m) => m.name);
  const voice = needing('voice');
  const sprite = needing('sprite');
  if (!voice.length && !sprite.length) return [];
  return [
    el('h3', {}, 'Still missing'),
    el(
      'ul',
      { className: 'menu-list' },
      voice.length > 0 &&
        el('li', {}, `No voice recorded yet for ${voice.join(', ')}. Their lines show as text.`),
      sprite.length > 0 &&
        el('li', {}, `No sprite yet for ${sprite.join(', ')}. They wear a stand-in.`),
    ),
  ];
}
