import type { Capabilities, CreatorApi } from './api';
import type { Appearance } from './character';
import { button, h, message } from './dom';
import { SpritePreview, lookEditor } from './look';

export const PLAYER_ID = 'player';

export class PlayerLookView {
  readonly root = h('div', { className: 'creator-screen creator-player' });
  private readonly body = h('section', { className: 'creator-section' });
  private readonly note = h('p', { className: 'creator-note', 'aria-live': 'polite' });
  private readonly save = button('Save', () => void this.store(), {
    className: 'creator-primary',
    disabled: true,
  });
  private readonly sprite: SpritePreview | null;
  private look: Appearance | null = null;
  private readonly api: CreatorApi;

  constructor(api: CreatorApi, capabilities: Capabilities | null, back: () => void) {
    this.api = api;
    this.sprite = capabilities?.kinds.sprite?.available ? new SpritePreview(api) : null;
    this.root.append(
      h(
        'header',
        { className: 'creator-bar' },
        button('← Library', back),
        h('h2', {}, 'Your look'),
        h('span', { className: 'creator-spacer' }),
        h('div', { className: 'creator-actions' }, this.save),
      ),
      h('p', { className: 'creator-hint' }, 'How you look to everyone in the village.'),
      this.note,
      this.body,
    );
    void this.load();
  }

  dispose(): void {
    this.sprite?.dispose();
  }

  private async load(): Promise<void> {
    try {
      this.draw(await this.api.player());
      void this.sprite?.show(PLAYER_ID);
    } catch (error) {
      this.note.textContent = `Couldn’t load your look: ${message(error)}`;
    }
  }

  private draw(look: Appearance): void {
    this.look = look;
    this.body.replaceChildren(
      lookEditor(look, (changed) => {
        this.look = changed;
        this.save.disabled = false;
        this.note.textContent = '';
      }),
      this.sprite?.root ?? '',
    );
  }

  private async store(): Promise<void> {
    if (!this.look) return;
    this.save.disabled = true;
    try {
      const saved = await this.api.savePlayer(this.look);
      this.note.textContent = 'Saved.';
      void this.sprite?.render(PLAYER_ID, saved);
    } catch (error) {
      this.save.disabled = false;
      this.note.textContent = `Couldn’t save: ${message(error)}`;
    }
  }
}
