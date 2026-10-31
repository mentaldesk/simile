import type { ChatBox } from './chat-box';
import type { Dialogue } from './dialogue';
import type { DialogueLog, LogEntry } from './log';
import { LOG_LIMIT } from './tuning';
import { PLAYER_ID } from './world-view';

export class LogPanel {
  private readonly panel: HTMLElement;
  private readonly list: HTMLOListElement;
  private reading = false;
  readonly stop: () => void;

  constructor(parent: HTMLElement, log: DialogueLog) {
    const panel = (this.panel = parent.appendChild(document.createElement('section')));
    panel.className = 'dialogue-log';
    panel.ariaLabel = 'Conversation log';
    panel.hidden = true;
    this.list = panel.appendChild(document.createElement('ol'));
    log.entries.forEach((entry) => this.append(entry));
    this.stop = log.onAdd((entry) => this.append(entry));
  }

  /** Whether the player opened the log to read it, with nobody to talk to. */
  get isReading(): boolean {
    return this.reading;
  }

  toggle(): void {
    this.reading = !this.reading;
  }

  close(): void {
    this.reading = false;
  }

  /** Shown while the player reads it, talks with someone or types to them, scrolled to the latest line. */
  update(chat: Pick<ChatBox, 'isOpen'>, dialogue: Pick<Dialogue, 'partner'>): void {
    const shown = this.reading || chat.isOpen || dialogue.partner() !== undefined;
    if (shown === !this.panel.hidden) return;
    this.panel.hidden = !shown;
    if (shown) this.list.scrollTop = this.list.scrollHeight;
  }

  private append(entry: LogEntry): void {
    const list = this.list;
    const following = list.scrollTop + list.clientHeight >= list.scrollHeight - 4;
    const item = list.appendChild(document.createElement('li'));
    item.classList.toggle('dialogue-log-player', entry.speaker === PLAYER_ID);
    const who = item.appendChild(document.createElement('b'));
    who.textContent = entry.to ? `${entry.name} → ${entry.to}` : entry.name;
    item.append(` ${entry.text}`);
    while (list.childElementCount > LOG_LIMIT) list.firstElementChild?.remove();
    if (following) list.scrollTop = list.scrollHeight;
  }
}
