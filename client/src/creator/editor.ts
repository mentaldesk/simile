import type { Capabilities, CreatorApi, GenerationEvent, Suggestion } from './api';
import type { Character } from './character';
import { type Child, button, h, humanise, message } from './dom';
import { Draft, SECTIONS, type Section, TITLES } from './draft';
import { Generation, passages } from './generation';
import { SpritePreview, lookEditor } from './look';
import { SampleLine } from './sample-line';
import { age, backgroundView, biographyView } from './story';
import { valuesView } from './values-view';
import { VoiceStep } from './voice';

export type EditorContext = {
  api: CreatorApi;
  capabilities: Capabilities | null;
  back: () => void;
  saved: (character: Character) => void;
  deleted: (id: string) => void;
};

type Confirm = { text: string; yes: string; action: () => void };

const PASSAGES: Record<string, string> = {
  persona: 'How they come across',
  speaking_style: 'How they speak',
  past: 'Life events',
  hooks: 'Ties',
  reference_line: 'Their line',
  description: 'Their voice',
  form: 'What they make',
  notes: 'The critic’s notes',
};

export class Editor {
  readonly root = h('div', { className: 'creator-screen creator-editor' });
  private readonly draft: Draft;
  private readonly readOnly: boolean;
  private readonly ctx: EditorContext;
  private readonly title = h('h2', {});
  private readonly status = h('span', { className: 'creator-status' });
  private readonly actions = h('div', { className: 'creator-actions' });
  private readonly messages = h('div', { className: 'creator-messages', 'aria-live': 'polite' });
  private readonly progress = h('div', { className: 'creator-generation', hidden: true });
  private readonly sections = h('fieldset', { className: 'creator-sections' });
  private readonly bodies = {} as Record<Section, HTMLElement>;
  private readonly heads = {} as Record<Section, HTMLElement>;
  private readonly voice: VoiceStep;
  private readonly sprite: SpritePreview | null;
  private readonly sample: SampleLine | null = null;
  private generation: Generation | null = null;
  private ticker: ReturnType<typeof setInterval> | undefined;
  private saving = false;
  private notice: Child = '';
  private problems: string[] = [];
  private confirm: Confirm | null = null;
  private drawnLook: string | null = null;
  private readonly unsaved = (event: BeforeUnloadEvent) => {
    if (!this.readOnly && (this.draft.dirty || this.generation?.running)) event.preventDefault();
  };

  constructor(ctx: EditorContext, draft: Draft, readOnly = false) {
    this.ctx = ctx;
    this.draft = draft;
    this.readOnly = readOnly;
    this.voice = new VoiceStep({
      api: ctx.api,
      capabilities: ctx.capabilities,
      draft,
      readOnly,
      edit: (voice) => this.edit('voice', { voice }),
      ensureSaved: () =>
        this.draft.saved && !this.draft.dirty ? Promise.resolve(true) : this.save(),
      picked: (character, description) => this.picked(character, description),
    });
    const sprites = ctx.capabilities?.kinds.sprite?.available ?? false;
    this.sprite = sprites && !readOnly ? new SpritePreview(ctx.api) : null;
    if (!readOnly)
      this.sample = new SampleLine((values, signal) => this.sampleLine(values, signal));

    const back = button('← Library', () => this.leave());
    this.root.append(
      h(
        'header',
        { className: 'creator-bar' },
        back,
        this.title,
        this.status,
        h('span', { className: 'creator-spacer' }),
        this.actions,
      ),
      h(
        'nav',
        { className: 'creator-jump' },
        SECTIONS.map((s) =>
          button(TITLES[s], () =>
            this.bodies[s].parentElement?.scrollIntoView({ behavior: 'smooth' }),
          ),
        ),
      ),
      this.messages,
      this.progress,
      this.sections,
    );
    for (const section of SECTIONS) {
      this.heads[section] = h('div', { className: 'creator-section-tools' });
      this.bodies[section] = h('div', { className: 'creator-section-body' });
      this.sections.append(
        h(
          'section',
          { className: 'creator-section', 'data-section': section },
          h('header', {}, h('h3', {}, TITLES[section]), this.heads[section]),
          this.bodies[section],
        ),
      );
    }
    this.renderAll();
    if (this.sprite && draft.saved) {
      void this.sprite.show(draft.saved.id).then((found) => {
        if (found) this.drawnLook = JSON.stringify(draft.saved?.appearance);
      });
    }
    window.addEventListener('beforeunload', this.unsaved);
  }

  dispose(): void {
    window.removeEventListener('beforeunload', this.unsaved);
    clearInterval(this.ticker);
    this.generation?.cancel();
    this.sample?.dispose();
    this.voice.dispose();
    this.sprite?.dispose();
  }

  private renderAll(): void {
    const disabled = this.readOnly;
    const w = this.draft.work;
    const look = h(
      'div',
      {},
      lookEditor(w.appearance!, (appearance) => this.edit('look', { appearance }), disabled),
    );
    if (this.sprite) look.append(this.sprite.root);
    this.bodies.look.replaceChildren(look);
    this.sample?.setValues({ ...w.values });
    this.bodies.values.replaceChildren(
      valuesView({
        draft: this.draft,
        sample: this.draft.written ? this.sample : null,
        disabled,
        onValues: (values) => {
          this.edit('values', { values });
          if (this.draft.written) this.sample?.changed(values);
        },
        onTraits: (traits) => this.edit('values', { traits }),
      }),
    );
    this.bodies.background.replaceChildren(
      backgroundView(this.draft, (patch) => this.edit('background', patch), disabled),
    );
    this.bodies.biography.replaceChildren(
      biographyView(
        this.draft,
        (patch) => this.edit('biography', patch),
        disabled,
        (s, accepted) => this.suggestion(s, accepted),
      ),
    );
    this.voice.render();
    this.bodies.voice.replaceChildren(this.voice.root);
    this.refresh();
  }

  private refresh(): void {
    const d = this.draft;
    const busy = this.generation?.running ?? false;
    const years = age(d.work);
    this.title.textContent = d.work.name?.trim() || 'New character';
    if (years !== null && d.work.occupation)
      this.title.append(h('small', {}, ` ${years}, ${d.work.occupation}`));
    this.status.textContent = this.readOnly
      ? 'Premade, read-only'
      : this.saving
        ? 'Saving…'
        : busy
          ? 'Writing…'
          : !d.written
            ? 'Not written yet'
            : d.dirty
              ? 'Unsaved changes'
              : 'Saved';
    this.sections.disabled = busy || this.saving;
    this.actions.replaceChildren(...(this.readOnly ? [] : this.actionButtons(busy)));
    for (const section of SECTIONS)
      this.heads[section].replaceChildren(
        ...(this.readOnly ? [] : this.sectionTools(section, busy)),
      );
    this.drawMessages();
  }

  private actionButtons(busy: boolean): HTMLElement[] {
    const d = this.draft;
    const buttons: HTMLElement[] = [];
    if (!d.written) {
      buttons.push(
        button('Write character', () => void this.write(), {
          className: 'creator-primary',
          disabled: busy,
          title: 'Claude writes everything that isn’t locked: two calls, about a minute.',
        }),
      );
    } else {
      const rerolls = d.rerolls(d.unlocked());
      buttons.push(
        button('Reroll unlocked', () => void this.write(d.unlocked()), {
          disabled: busy || !rerolls.length,
          title: rerolls.length ? `Writes ${rerolls.join(', ')} again.` : 'Everything is locked.',
        }),
      );
    }
    buttons.push(
      button('Save', () => void this.save(), {
        className: d.written ? 'creator-primary' : '',
        disabled: busy || this.saving || !d.dirty,
      }),
    );
    if (d.saved) {
      buttons.push(
        h(
          'a',
          {
            className: 'creator-button',
            href: this.ctx.api.exportUrl(d.saved.id),
            download: `${d.saved.id}.zip`,
            title: 'A zip of the character and its voice clip',
          },
          'Export',
        ),
        button('Delete', () => this.askDelete(), { disabled: busy }),
      );
    }
    return buttons;
  }

  private sectionTools(section: Section, busy: boolean): HTMLElement[] {
    const d = this.draft;
    const locked = d.locked(section);
    const lock = button(
      locked ? 'Locked' : 'Lock',
      () => {
        d.setLocked(section, !locked);
        this.refresh();
      },
      {
        className: 'creator-lock',
        'aria-pressed': String(locked),
        disabled: busy,
        title: locked
          ? 'Kept as it is when anything is written again. Click to unlock.'
          : 'Keep this as it is when anything is written again.',
      },
    );
    if (!d.written) return [lock];
    const asked = d.rerolls([section]);
    const reroll = button('Reroll', () => void this.write([section]), {
      disabled: busy || !asked.length,
      title: asked.length ? `Writes ${asked.join(', ')} again.` : 'Unlock it to reroll it.',
    });
    return [lock, reroll];
  }

  private drawMessages(): void {
    const parts: Child[] = [];
    if (this.confirm) {
      const { text, yes, action } = this.confirm;
      parts.push(
        h(
          'div',
          { className: 'creator-confirm' },
          h('span', {}, text),
          button(
            yes,
            () => {
              this.confirm = null;
              action();
            },
            { className: 'creator-danger' },
          ),
          button('Cancel', () => {
            this.confirm = null;
            this.drawMessages();
          }),
        ),
      );
    }
    if (this.problems.length) {
      parts.push(
        h(
          'div',
          { className: 'creator-problems' },
          h('b', {}, 'Not saved yet:'),
          h(
            'ul',
            {},
            this.problems.map((p) => h('li', {}, p)),
          ),
        ),
      );
    }
    if (this.draft.warnings.length)
      parts.push(h('p', { className: 'creator-warn' }, this.draft.warnings.join(' ')));
    if (this.notice) parts.push(h('p', { className: 'creator-note' }, this.notice));
    this.messages.replaceChildren(...parts.filter((p): p is HTMLElement | string => !!p));
  }

  private edit(section: Section, patch: Partial<Character>): void {
    this.draft.edit(section, patch);
    this.problems = [];
    this.notice = '';
    this.refresh();
  }

  private suggestion(suggestion: Suggestion, accepted: boolean): void {
    if (accepted) this.draft.accept(suggestion);
    else this.draft.ignore(suggestion);
    this.bodies.biography.replaceChildren(
      biographyView(
        this.draft,
        (patch) => this.edit('biography', patch),
        this.readOnly,
        (s, a) => this.suggestion(s, a),
      ),
    );
    this.refresh();
  }

  private async write(sections?: readonly Section[]): Promise<void> {
    const d = this.draft;
    const generation = new Generation();
    const asked = d.written ? d.rerolls(sections ?? d.unlocked()) : undefined;
    if (asked && !asked.length) return;
    const events: AsyncIterable<GenerationEvent> = asked
      ? this.ctx.api.reroll(d.character(), asked, generation.signal)
      : this.ctx.api.generate(d.brief(), generation.signal);
    this.generation = generation;
    this.notice = '';
    this.problems = [];
    generation.onChange = () => this.drawGeneration();
    this.ticker = setInterval(() => this.drawGeneration(), 1000);
    this.drawGeneration();
    this.refresh();
    const result = await generation.run(events);
    clearInterval(this.ticker);
    if (result) {
      d.apply(result, asked);
      this.notice = generation.status();
      this.generation = null;
      this.progress.hidden = true;
      this.renderAll();
    } else {
      this.drawGeneration();
      this.refresh();
    }
  }

  private drawGeneration(): void {
    const g = this.generation;
    if (!g) return;
    this.progress.hidden = false;
    const text = h('div', { className: 'creator-stream' });
    let last = '';
    for (const { key, text: passage } of passages(g.text)) {
      if (key !== last) text.append(h('b', {}, PASSAGES[key] ?? humanise(key)));
      text.append(h('p', {}, passage));
      last = key;
    }
    const waiting =
      g.state === 'thinking' && g.purpose === 'character-biography'
        ? h(
            'p',
            { className: 'creator-hint' },
            'Claude thinks before it writes, so the first words can take about a minute.',
          )
        : '';
    const done = !g.running;
    this.progress.replaceChildren(
      h(
        'div',
        { className: 'creator-generation-head' },
        h('b', {}, g.status()),
        done
          ? button('Dismiss', () => {
              this.generation = null;
              this.progress.hidden = true;
              this.refresh();
            })
          : button('Cancel', () => g.cancel()),
      ),
      waiting,
      text,
    );
    text.scrollTop = text.scrollHeight;
  }

  private async sampleLine(values: Record<string, number>, signal: AbortSignal): Promise<string> {
    if (this.generation?.running) throw new Error('wait for the writing to finish');
    const character = { ...this.draft.character(), values };
    for await (const event of this.ctx.api.reroll(character, ['voice'], signal)) {
      if (event.type === 'done') return event.character.voice.reference_line;
      if (event.type === 'error') throw new Error(event.error);
    }
    throw new Error('the server stopped before it finished');
  }

  async save(): Promise<boolean> {
    const d = this.draft;
    this.problems = d.problems();
    if (this.problems.length) {
      this.refresh();
      return false;
    }
    this.saving = true;
    this.notice = '';
    this.refresh();
    try {
      const character = d.saved
        ? await this.ctx.api.update(d.character())
        : await this.ctx.api.create(d.character());
      d.markSaved(character);
      this.ctx.saved(character);
      this.notice = 'Saved.';
      const look = JSON.stringify(character.appearance);
      if (this.sprite && look !== this.drawnLook) {
        this.drawnLook = look;
        void this.sprite.render(character.id, character.appearance);
      }
      return true;
    } catch (error) {
      this.notice = `Couldn’t save: ${message(error)}`;
      return false;
    } finally {
      this.saving = false;
      this.voice.render();
      this.refresh();
    }
  }

  private async picked(character: Character, description?: string): Promise<void> {
    this.draft.markVoice(character, description);
    this.ctx.saved(character);
    if (this.draft.dirty) await this.save();
    this.refresh();
  }

  private askDelete(): void {
    const saved = this.draft.saved;
    if (!saved) return;
    this.confirm = {
      text: `Delete ${saved.name} and their voice for good?`,
      yes: 'Delete',
      action: async () => {
        try {
          await this.ctx.api.remove(saved.id);
          this.ctx.deleted(saved.id);
        } catch (error) {
          this.notice = `Couldn’t delete: ${message(error)}`;
          this.refresh();
        }
      },
    };
    this.drawMessages();
  }

  private leave(): void {
    if (this.readOnly || !this.draft.dirty) {
      this.ctx.back();
      return;
    }
    this.confirm = {
      text: 'Leave without saving your changes?',
      yes: 'Leave',
      action: () => this.ctx.back(),
    };
    this.drawMessages();
  }
}

export function editorFor(ctx: EditorContext, character: Character | null): Editor {
  if (!character) return new Editor(ctx, Draft.blank());
  return new Editor(ctx, Draft.of(character), character.source === 'premade');
}
