import type { Capabilities, CreatorApi } from './api';
import type { Appearance } from './character';
import { button, h, message } from './dom';
import { DollPreview, lookEditor } from './look';

export const PLAYER_ID = 'player';

export class PlayerLookView {
  readonly root = h('div', { className: 'creator-screen creator-player' });
  private readonly body = h('section', { className: 'creator-section' });
  private readonly note = h('p', { className: 'creator-note', 'aria-live': 'polite' });
  private readonly save = button('Save', () => void this.store(), {
    className: 'creator-primary',
    disabled: true,
  });
  private readonly doll: DollPreview;
  private readonly paints: boolean;
  private look: Appearance | null = null;
  private readonly api: CreatorApi;

  constructor(api: CreatorApi, capabilities: Capabilities | null, back: () => void) {
    this.api = api;
    this.doll = new DollPreview(api);
    this.paints = capabilities?.kinds.doll?.available ?? false;
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
    this.doll.dispose();
  }

  private async load(): Promise<void> {
    try {
      this.draw(await this.api.player());
      if (this.paints) void this.doll.show(PLAYER_ID);
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
        this.doll.preview(changed, PLAYER_ID);
      }),
      this.doll.root,
    );
    this.doll.preview(look, PLAYER_ID);
  }

  private async store(): Promise<void> {
    if (!this.look) return;
    this.save.disabled = true;
    try {
      const saved = await this.api.savePlayer(this.look);
      this.note.textContent = 'Saved.';
      if (this.paints) void this.doll.paint(PLAYER_ID, saved);
    } catch (error) {
      this.save.disabled = false;
      this.note.textContent = `Couldn’t save: ${message(error)}`;
    }
  }
}
