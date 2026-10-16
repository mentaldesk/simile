import type { Dialogue } from './dialogue';

const HINT_MS = 2500;
const INVITATION_MS = 6000;

export class ChatBox {
  private readonly form: HTMLFormElement;
  private readonly to: HTMLElement;
  private readonly input: HTMLInputElement;
  private readonly hint: HTMLElement;
  private readonly dialogue: Dialogue;
  private readonly findTarget: () => string | undefined;
  private target: string | undefined;
  private hideHint?: ReturnType<typeof setTimeout>;

  constructor(parent: HTMLElement, dialogue: Dialogue, findTarget: () => string | undefined) {
    this.dialogue = dialogue;
    this.findTarget = findTarget;

    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'dialogue-hint';
    this.hint.hidden = true;

    this.form = parent.appendChild(document.createElement('form'));
    this.form.className = 'dialogue-chat';
    this.form.hidden = true;
    const label = this.form.appendChild(document.createElement('label'));
    this.to = label.appendChild(document.createElement('span'));
    this.input = label.appendChild(document.createElement('input'));
    this.input.maxLength = 500;
    this.input.autocomplete = 'off';

    // Typing mustn't reach the game's keys. Key-ups still do, so no key gets stuck down.
    this.input.addEventListener('keydown', (event) => {
      event.stopPropagation();
      if (event.key === 'Escape') this.close();
    });
    this.form.addEventListener('submit', (event) => {
      event.preventDefault();
      this.send();
    });
  }

  get isOpen(): boolean {
    return !this.form.hidden;
  }

  open(target = this.findTarget()): void {
    if (!target) {
      this.flash('Nobody nearby is free to talk.');
      return;
    }
    this.target = target;
    this.to.textContent = `To ${this.dialogue.nameOf(target)}:`;
    this.form.hidden = false;
    this.input.focus();
  }

  close(): void {
    this.form.hidden = true;
    this.input.value = '';
    this.input.blur();
    this.target = undefined;
  }

  private send(): void {
    if (!this.target || !this.input.value.trim()) {
      this.close();
    } else if (this.dialogue.say(this.input.value, this.target)) {
      this.close();
    } else {
      this.flash("Not connected, so that wasn't sent.");
    }
  }

  invite(npcId: string): void {
    if (this.isOpen) return;
    const name = this.dialogue.nameOf(npcId);
    this.flash(`${name} wants to talk. Press Enter to reply.`, INVITATION_MS);
  }

  private flash(message: string, ms = HINT_MS): void {
    this.hint.textContent = message;
    this.hint.hidden = false;
    clearTimeout(this.hideHint);
    this.hideHint = setTimeout(() => (this.hint.hidden = true), ms);
  }
}
