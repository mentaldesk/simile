import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { Values } from './character';
import { SampleLine } from './sample-line';

type Ask = (values: Values, signal: AbortSignal) => Promise<string>;

const values = (n: number) => ({ honesty: n });

describe('the sample line', () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it('waits for the sliders to be still before asking', async () => {
    const ask = vi.fn<Ask>(async () => 'A line.');
    const sample = new SampleLine(ask, 1000, 4);
    sample.changed(values(0.1));
    sample.changed(values(0.2));
    await vi.advanceTimersByTimeAsync(999);
    sample.changed(values(0.3));
    await vi.advanceTimersByTimeAsync(999);
    expect(ask).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);
    expect(ask).toHaveBeenCalledOnce();
    expect(ask.mock.calls[0][0]).toEqual(values(0.3));
    expect(sample.line).toBe('A line.');
    expect(sample.state).toBe('ready');
  });

  it('never asks twice at once, and catches up afterwards', async () => {
    let finish!: (line: string) => void;
    const ask = vi.fn<Ask>(() => new Promise<string>((resolve) => (finish = resolve)));
    const sample = new SampleLine(ask, 1000, 4);
    sample.changed(values(0.1));
    await vi.advanceTimersByTimeAsync(1000);
    sample.changed(values(0.2));
    await vi.advanceTimersByTimeAsync(5000);
    expect(ask).toHaveBeenCalledOnce();
    expect(sample.stale).toBe(true);
    finish('First.');
    await vi.advanceTimersByTimeAsync(1000);
    expect(ask).toHaveBeenCalledTimes(2);
    expect(ask.mock.calls[1][0]).toEqual(values(0.2));
  });

  it('stops asking by itself after a few lines, but the button still works', async () => {
    const ask = vi.fn<Ask>(async () => 'A line.');
    const sample = new SampleLine(ask, 1000, 2);
    for (const n of [0.1, 0.2, 0.3, 0.4]) {
      sample.changed(values(n));
      await vi.advanceTimersByTimeAsync(1000);
    }
    expect(ask).toHaveBeenCalledTimes(2);
    expect(sample.autoLeft).toBe(0);
    expect(sample.stale).toBe(true);
    await sample.request();
    expect(ask).toHaveBeenCalledTimes(3);
    expect(ask.mock.calls[2][0]).toEqual(values(0.4));
  });

  it('shows why a line failed', async () => {
    const sample = new SampleLine(async () => Promise.reject(new Error('busy')), 1000, 4);
    sample.setValues(values(0.5));
    await sample.request();
    expect(sample.state).toBe('failed');
    expect(sample.error).toBe('busy');
  });

  it('asks for nothing after it’s disposed', async () => {
    const ask = vi.fn<Ask>(async () => 'A line.');
    const sample = new SampleLine(ask, 1000, 4);
    sample.changed(values(0.1));
    sample.dispose();
    await vi.advanceTimersByTimeAsync(5000);
    expect(ask).not.toHaveBeenCalled();
  });
});
