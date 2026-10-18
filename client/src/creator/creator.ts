import type { Capabilities, CreatorApi } from './api';
import type { Character } from './character';
import { h } from './dom';
import { type Editor, editorFor } from './editor';
import { LibraryView } from './library';
import { PlayerLookView } from './player-look';
import './creator.css';

export class Creator {
  readonly root = h('div', { className: 'creator', tabIndex: -1 });
  private readonly library: LibraryView;
  private screen: Editor | PlayerLookView | null = null;
  private readonly capabilities: Promise<Capabilities | null>;
  private readonly api: CreatorApi;

  constructor(parent: HTMLElement, api: CreatorApi) {
    this.api = api;
    // Typing mustn't reach the game's keys. Key-ups still do, so no key gets stuck down.
    this.root.addEventListener('keydown', (event) => event.stopPropagation());
    this.capabilities = api.capabilities().catch(() => null);
    this.library = new LibraryView(api, {
      open: (character) => void this.open(character),
      look: async () =>
        this.show(new PlayerLookView(api, await this.capabilities, () => this.home())),
      imported: (character) => void this.open(character),
    });
    this.root.append(this.library.root);
    parent.append(this.root);
  }

  remove(): void {
    this.screen?.dispose();
    this.root.remove();
  }

  private async open(character: Character | null): Promise<void> {
    const editor = editorFor(
      {
        api: this.api,
        capabilities: await this.capabilities,
        back: () => this.home(),
        saved: () => void this.library.load(),
        deleted: (id) => {
          this.home();
          this.library.say(`Deleted ${character?.name ?? id}.`);
        },
      },
      character,
    );
    this.show(editor);
  }

  private show(screen: Editor | PlayerLookView): void {
    this.screen?.dispose();
    this.screen = screen;
    this.library.root.hidden = true;
    this.root.append(screen.root);
    this.root.scrollTop = 0;
  }

  private home(): void {
    this.screen?.dispose();
    this.screen?.root.remove();
    this.screen = null;
    this.library.root.hidden = false;
    void this.library.load();
  }
}
