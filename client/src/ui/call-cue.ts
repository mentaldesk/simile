import './call-cue.css';

/** "Mei wants to talk." at the top of each panel, while that resident is trying to talk to the player. */
export class CallCue {
  private readonly slots = new Set<WeakRef<HTMLElement>>();
  private caller?: string;
  private text = '';

  /** Gives a panel a line at its top for the cue. */
  slot(panel: HTMLElement): void {
    const slot = document.createElement('aside');
    slot.className = 'call-cue';
    slot.setAttribute('role', 'status');
    panel.prepend(slot);
    this.slots.add(new WeakRef(slot));
    this.render();
  }

  show(npcId: string, name: string): void {
    this.caller = npcId;
    this.text = `${name} wants to talk. Esc, then Enter to reply.`;
    this.render();
  }

  /** Hides the cue once the caller isn't the player's partner any more. */
  update(partner: string | undefined): void {
    if (this.caller === undefined || partner === this.caller) return;
    this.caller = undefined;
    this.render();
  }

  private render(): void {
    for (const ref of this.slots) {
      const slot = ref.deref();
      if (!slot) {
        this.slots.delete(ref);
        continue;
      }
      slot.hidden = this.caller === undefined;
      slot.textContent = this.caller === undefined ? '' : this.text;
    }
  }
}

export const callCue = new CallCue();
