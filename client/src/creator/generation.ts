import type { GenerationEvent, Written } from './api';

export type GenerationState = 'starting' | 'thinking' | 'writing' | 'done' | 'failed' | 'cancelled';

const PURPOSES: Record<string, string> = {
  'character-biography': 'Writing',
  'character-critic': 'The critic is reading it',
};

export class Generation {
  state: GenerationState = 'starting';
  purpose: string | null = null;
  calls = 0;
  text = '';
  error: string | null = null;
  result: Written | null = null;
  onChange: () => void = () => {};
  readonly started: number;
  callStarted: number;
  private readonly controller = new AbortController();
  private readonly now: () => number;

  constructor(now: () => number = Date.now) {
    this.now = now;
    this.started = this.callStarted = now();
  }

  get signal(): AbortSignal {
    return this.controller.signal;
  }

  get running(): boolean {
    return this.state === 'starting' || this.state === 'thinking' || this.state === 'writing';
  }

  async run(events: AsyncIterable<GenerationEvent>): Promise<Written | null> {
    try {
      for await (const event of events) {
        this.take(event);
        if (!this.running) break;
      }
      if (this.running) this.fail('The server stopped before it finished');
    } catch (error) {
      if (this.state !== 'cancelled')
        this.fail(error instanceof Error ? error.message : String(error));
    }
    return this.result;
  }

  take(event: GenerationEvent): void {
    switch (event.type) {
      case 'call':
        this.purpose = event.purpose;
        this.calls += 1;
        this.text = '';
        this.callStarted = this.now();
        this.state = 'thinking';
        break;
      case 'text':
        this.text += event.text;
        this.state = 'writing';
        break;
      case 'done':
        this.result = event;
        this.state = 'done';
        break;
      case 'error':
        this.fail(event.error);
        return;
    }
    this.onChange();
  }

  cancel(): void {
    if (!this.running) return;
    this.state = 'cancelled';
    this.controller.abort();
    this.onChange();
  }

  status(): string {
    const seconds = (since: number) => `${Math.round((this.now() - since) / 1000)} s`;
    const call = this.purpose ? (PURPOSES[this.purpose] ?? this.purpose) : 'Starting';
    switch (this.state) {
      case 'starting':
        return `Starting · ${seconds(this.started)}`;
      case 'thinking':
        return `${call} · thinking first, ${seconds(this.callStarted)}`;
      case 'writing':
        return `${call} · ${seconds(this.callStarted)}`;
      case 'done':
        return `Done in ${seconds(this.started)}`;
      case 'failed':
        return `Failed: ${this.error}`;
      case 'cancelled':
        return 'Cancelled';
    }
  }

  private fail(error: string): void {
    this.error = error;
    this.state = 'failed';
    this.onChange();
  }
}

export type Passage = { key: string; text: string };

/** The strings in a reply that may be cut off part-way, by key, to show it as prose. */
export function passages(json: string): Passage[] {
  const found: Passage[] = [];
  const open: { object: boolean; key: string | null }[] = [];
  let key: string | null = null;
  let expectKey = false;
  let i = 0;
  while (i < json.length) {
    const char = json[i];
    if (char === '"') {
      const [text, end] = readString(json, i + 1);
      i = end;
      if (expectKey) {
        key = text;
        expectKey = false;
      } else {
        found.push({ key: key ?? enclosingKey(open), text });
      }
      continue;
    }
    if (char === '{' || char === '[') {
      open.push({ object: char === '{', key });
      key = null;
      expectKey = char === '{';
    } else if (char === '}' || char === ']') {
      open.pop();
      key = null;
      expectKey = false;
    } else if (char === ',') {
      const inObject = open.at(-1)?.object ?? false;
      if (inObject) key = null;
      expectKey = inObject;
    }
    i += 1;
  }
  return found;
}

function enclosingKey(open: { key: string | null }[]): string {
  for (let i = open.length - 1; i >= 0; i--) {
    const key = open[i].key;
    if (key !== null) return key;
  }
  return '';
}

function readString(json: string, start: number): [string, number] {
  let text = '';
  let i = start;
  while (i < json.length) {
    const char = json[i];
    if (char === '"') return [text, i + 1];
    if (char === '\\') {
      const next = json[i + 1];
      if (next === undefined) break;
      if (next === 'u') {
        const hex = json.slice(i + 2, i + 6);
        if (hex.length < 4) break;
        text += String.fromCharCode(parseInt(hex, 16));
        i += 6;
        continue;
      }
      text += ESCAPES[next] ?? next;
      i += 2;
      continue;
    }
    text += char;
    i += 1;
  }
  return [text, json.length];
}

const ESCAPES: Record<string, string> = { n: '\n', t: '\t', r: '', b: '', f: '' };
