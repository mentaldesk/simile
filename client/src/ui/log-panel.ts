import type { DialogueLog, LogEntry } from './log';
import { LOG_LIMIT } from './tuning';
import { PLAYER_ID } from './world-view';

export class LogPanel {
  private readonly list: HTMLOListElement;
  readonly stop: () => void;

  constructor(parent: HTMLElement, log: DialogueLog) {
    const panel = parent.appendChild(document.createElement('section'));
    panel.className = 'dialogue-log';
    panel.ariaLabel = 'Conversation log';
    this.list = panel.appendChild(document.createElement('ol'));
    log.entries.forEach((entry) => this.append(entry));
    this.stop = log.onAdd((entry) => this.append(entry));
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
