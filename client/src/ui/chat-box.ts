import type { Dialogue } from './dialogue';
import type { ChatTarget, Refusal } from './target';

const HINT_MS = 2500;
const INVITATION_MS = 6000;

export class ChatBox {
  private readonly form: HTMLFormElement;
  private readonly to: HTMLElement;
  private readonly input: HTMLInputElement;
  private readonly hint: HTMLElement;
  private readonly dialogue: Dialogue;
  private readonly targets: ChatTarget;
  private hideHint?: ReturnType<typeof setTimeout>;

  constructor(parent: HTMLElement, dialogue: Dialogue, targets: ChatTarget) {
    this.dialogue = dialogue;
    this.targets = targets;

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
      if (event.key === 'Escape') {
        this.clear();
      } else if (event.key === 'Tab') {
        event.preventDefault();
        this.cycle(event.shiftKey ? -1 : 1);
      }
    });
    this.form.addEventListener('submit', (event) => {
      event.preventDefault();
      this.send();
    });
  }

  get isOpen(): boolean {
    return !this.form.hidden;
  }

  open(): void {
    if (!this.targets.hold()) {
      this.flash('Nobody nearby is free to talk.');
      return;
    }
    this.form.hidden = false;
    this.relabel();
  }

  close(): void {
    this.form.hidden = true;
    this.input.value = '';
    this.input.blur();
    this.targets.release();
  }

  /** Closes the box and forgets whom the player chose. */
  clear(): void {
    this.targets.clear();
    this.close();
  }

  choose(npcId: string): void {
    const refusal = this.targets.refusal(npcId);
    if (refusal) {
      this.refuse(npcId, refusal);
      return;
    }
    this.targets.choose(npcId);
    this.relabel();
  }

  cycle(step: 1 | -1): void {
    if (this.targets.cycle(step)) this.relabel();
    else this.flash('Nobody nearby is free to talk.');
  }

  invite(npcId: string): void {
    if (this.isOpen) return;
    this.targets.choose(npcId);
    const name = this.dialogue.nameOf(npcId);
    this.flash(`${name} wants to talk. Press Enter to reply.`, INVITATION_MS);
  }

  private relabel(): void {
    const target = this.targets.current();
    if (!this.isOpen || !target) return;
    this.to.textContent = `To ${this.dialogue.nameOf(target)}:`;
    this.input.focus();
  }

  private send(): void {
    const target = this.targets.current();
    const refusal = target && this.targets.refusal(target);
    if (!target || !this.input.value.trim()) {
      this.close();
    } else if (refusal) {
      this.refuse(target, refusal);
    } else if (this.dialogue.say(this.input.value, target)) {
      this.close();
    } else {
      this.flash("Not connected, so that wasn't sent.");
    }
  }

  private refuse(npcId: string, refusal: Refusal): void {
    const name = this.dialogue.nameOf(npcId);
    this.flash(
      refusal === 'busy' ? `${name} is talking with someone else.` : `${name} is too far away.`,
    );
  }

  private flash(message: string, ms = HINT_MS): void {
    this.hint.textContent = message;
    this.hint.hidden = false;
    clearTimeout(this.hideHint);
    this.hideHint = setTimeout(() => (this.hint.hidden = true), ms);
  }
}
