import { describe, expect, it } from 'vitest';
import { JITTER_BUFFER_S, Timeline } from './timeline';

const CHUNK = 2400;
const CHUNK_S = 0.1;

describe('Timeline', () => {
  it('starts the first chunk a jitter buffer after it arrives', () => {
    expect(new Timeline().place(3, CHUNK)).toEqual({ at: 3 + JITTER_BUFFER_S, late: false });
  });

  it('places later chunks back to back however unevenly they arrive', () => {
    const timeline = new Timeline();
    const arrivals = [0, 0.01, 0.15, 0.16, 0.39];

    const starts = arrivals.map((now) => timeline.place(now, CHUNK));

    expect(starts.map(({ at }) => at)).toEqual(
      arrivals.map((_, i) => expect.closeTo(JITTER_BUFFER_S + i * CHUNK_S, 12)),
    );
    expect(starts.some(({ late }) => late)).toBe(false);
  });

  it('works out times from the sample count, so they never drift', () => {
    const timeline = new Timeline();
    for (let i = 0; i < 36_000; i++) timeline.place(0, 2401);

    expect(timeline.end).toBe(JITTER_BUFFER_S + (36_000 * 2401) / 24_000);
  });

  it('handles chunks of any length', () => {
    const timeline = new Timeline();
    timeline.place(0, 1);
    timeline.place(0, 24_000);

    expect(timeline.place(0, 7).at).toBeCloseTo(JITTER_BUFFER_S + 1 + 1 / 24_000, 12);
  });

  it('buffers again after a chunk arrives too late to follow on', () => {
    const timeline = new Timeline();
    timeline.place(0, CHUNK);

    expect(timeline.place(0.5, CHUNK)).toEqual({ at: 0.5 + JITTER_BUFFER_S, late: true });
    expect(timeline.place(0.55, CHUNK).at).toBeCloseTo(0.5 + JITTER_BUFFER_S + CHUNK_S, 12);
  });

  it('counts a chunk due too soon to schedule safely as late', () => {
    const timeline = new Timeline();
    timeline.place(0, CHUNK);

    expect(timeline.place(JITTER_BUFFER_S + CHUNK_S - 0.001, CHUNK).late).toBe(true);
  });

  it('ends before anything is placed', () => {
    expect(new Timeline().end).toBe(-Infinity);
  });
});
