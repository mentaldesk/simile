import { LOG_LIMIT } from './tuning';

export type LogEntry = { speaker: string; name: string; text: string; to: string | null };

export class DialogueLog {
  private readonly items: LogEntry[] = [];
  private readonly listeners = new Set<(entry: LogEntry) => void>();

  get entries(): readonly LogEntry[] {
    return this.items;
  }

  add(entry: LogEntry): void {
    this.items.push(entry);
    if (this.items.length > LOG_LIMIT) this.items.shift();
    for (const listener of this.listeners) listener(entry);
  }

  onAdd(listener: (entry: LogEntry) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
