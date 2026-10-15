import { SAMPLE_RATE } from '../net';

export const JITTER_BUFFER_S = 0.1;
const MIN_LEAD_S = 0.01;

/** Places a line's chunks back to back, a jitter buffer after the first and after any underrun. */
export class Timeline {
  private start = -Infinity;
  private samples = 0;

  get end(): number {
    return this.start + this.samples / SAMPLE_RATE;
  }

  place(now: number, length: number): { at: number; late: boolean } {
    const late = this.samples > 0 && this.end < now + MIN_LEAD_S;
    if (late || this.samples === 0) {
      this.start = now + JITTER_BUFFER_S;
      this.samples = 0;
    }
    const at = this.end;
    this.samples += length;
    return { at, late };
  }
}
