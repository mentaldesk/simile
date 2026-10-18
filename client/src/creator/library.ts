import type { CreatorApi } from './api';
import type { Character } from './character';
import { type Child, button, h, message } from './dom';

type Actions = {
  open: (character: Character | null) => void;
  look: () => void | Promise<void>;
  imported: (character: Character) => void;
};

const YEAR = () => new Date().getUTCFullYear();

export class LibraryView {
  readonly root = h('div', { className: 'creator-screen creator-library' });
  private readonly list = h('div', { className: 'creator-library-list' });
  private readonly note = h('p', { className: 'creator-note', 'aria-live': 'polite' });
  private characters: Character[] = [];
  private filter = '';
  private readonly api: CreatorApi;
  private readonly actions: Actions;

  constructor(api: CreatorApi, actions: Actions) {
    this.api = api;
    this.actions = actions;
    const upload = h('input', {
      type: 'file',
      accept: '.zip,application/zip',
      hidden: true,
      className: 'creator-import',
      onchange: (event) => void this.import(event.target as HTMLInputElement),
    });
    const search = h('input', {
      type: 'search',
      placeholder: 'Find by name, work or origin',
      'aria-label': 'Find a character',
      oninput: (event) => {
        this.filter = (event.target as HTMLInputElement).value.trim().toLowerCase();
        this.draw();
      },
    });
    this.root.append(
      h(
        'header',
        { className: 'creator-bar' },
        h('a', { className: 'creator-button', href: location.pathname }, '← Title'),
        h('h2', {}, 'Characters'),
        h('span', { className: 'creator-spacer' }),
        h(
          'div',
          { className: 'creator-actions' },
          button('Your look', () => actions.look()),
          button('Import…', () => upload.click(), {
            title: 'A character exported from Simile, as a .zip',
          }),
          button('New character', () => actions.open(null), { className: 'creator-primary' }),
          upload,
        ),
      ),
      search,
      this.note,
      this.list,
    );
    void this.load();
  }

  async load(): Promise<void> {
    try {
      this.characters = await this.api.characters();
      this.draw();
    } catch (error) {
      this.say(`Couldn’t load the library: ${message(error)}`);
    }
  }

  say(text: string): void {
    this.note.textContent = text;
  }

  private draw(): void {
    const matches = (c: Character) =>
      !this.filter ||
      [c.name, c.occupation, c.origin].some((s) => s.toLowerCase().includes(this.filter));
    const yours = this.characters.filter((c) => c.source === 'player' && matches(c));
    const premade = this.characters.filter((c) => c.source === 'premade' && matches(c));
    this.list.replaceChildren(
      h('h3', {}, 'Yours ', h('small', {}, String(yours.length))),
      yours.length
        ? this.cards(yours)
        : h(
            'p',
            { className: 'creator-hint' },
            this.filter ? 'None match.' : 'None yet. Make one, or import one.',
          ),
      h('h3', {}, 'Premade ', h('small', {}, `${premade.length}, read-only`)),
      premade.length ? this.cards(premade) : h('p', { className: 'creator-hint' }, 'None match.'),
    );
  }

  private cards(characters: Character[]): HTMLElement {
    return h(
      'ul',
      { className: 'creator-cards' },
      characters.map((c) =>
        h(
          'li',
          {},
          h(
            'button',
            { type: 'button', className: 'creator-card', onclick: () => this.actions.open(c) },
            h('b', {}, c.name),
            h('span', {}, `${YEAR() - c.birth_year}, ${c.occupation}`),
            h('span', { className: 'creator-origin' }, c.origin),
            badges(c),
          ),
        ),
      ),
    );
  }

  private async import(input: HTMLInputElement): Promise<void> {
    const file = input.files?.[0];
    input.value = '';
    if (!file) return;
    this.say(`Importing ${file.name}…`);
    try {
      const character = await this.api.importFile(file);
      this.say(`Imported ${character.name}.`);
      await this.load();
      this.actions.imported(character);
    } catch (error) {
      this.say(`Couldn’t import ${file.name}: ${message(error)}`);
    }
  }
}

function badges(c: Character): Child {
  const parts = [c.voice.reference_clip ? 'voice' : '', c.craft ? c.craft.medium : ''].filter(
    Boolean,
  );
  return parts.length ? h('small', { className: 'creator-badges' }, parts.join(' · ')) : null;
}
