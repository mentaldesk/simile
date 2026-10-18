import type { Values } from './character';

export type SampleState = 'idle' | 'waiting' | 'asking' | 'ready' | 'failed';

export const SAMPLE_DELAY_MS = 2500;
export const SAMPLE_AUTO_LIMIT = 4;

type Ask = (values: Values, signal: AbortSignal) => Promise<string>;

/** Each line is a Claude call: debounced, one at a time, and few without the button. */
export class SampleLine {
  line: string | null = null;
  state: SampleState = 'idle';
  error: string | null = null;
  stale = false;
  asked = 0;
  onChange: () => void = () => {};
  private values: Values | null = null;
  private timer: ReturnType<typeof setTimeout> | undefined;
  private controller: AbortController | null = null;
  private readonly ask: Ask;
  private readonly delay: number;
  private readonly limit: number;

  constructor(ask: Ask, delay = SAMPLE_DELAY_MS, limit = SAMPLE_AUTO_LIMIT) {
    this.ask = ask;
    this.delay = delay;
    this.limit = limit;
  }

  get autoLeft(): number {
    return Math.max(0, this.limit - this.asked);
  }

  changed(values: Values): void {
    this.values = values;
    this.stale = this.line !== null || this.state === 'asking';
    clearTimeout(this.timer);
    if (this.state !== 'asking' && this.autoLeft > 0) {
      this.state = 'waiting';
      this.timer = setTimeout(() => void this.request(true), this.delay);
    }
    this.onChange();
  }

  async request(automatic = false): Promise<void> {
    clearTimeout(this.timer);
    if (this.state === 'asking' || !this.values) return;
    if (automatic) this.asked += 1;
    const values = this.values;
    this.controller = new AbortController();
    this.state = 'asking';
    this.stale = false;
    this.error = null;
    this.onChange();
    try {
      this.line = await this.ask(values, this.controller.signal);
      this.state = 'ready';
    } catch (error) {
      if (this.controller.signal.aborted) return;
      this.state = 'failed';
      this.error = error instanceof Error ? error.message : String(error);
    }
    this.controller = null;
    if (this.values !== values) this.changed(this.values);
    else this.onChange();
  }

  setValues(values: Values): void {
    this.values = values;
  }

  dispose(): void {
    clearTimeout(this.timer);
    this.controller?.abort();
  }
}
