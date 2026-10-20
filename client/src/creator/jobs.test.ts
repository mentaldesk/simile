import { describe, expect, it, vi } from 'vitest';
import { type Job, JobWatch, type SocketLike, UNKNOWN_JOB, describe as describeJob } from './jobs';

function job(overrides: Partial<Job> = {}): Job {
  return {
    id: '3f9c2a7d1b6e4c08',
    kind: 'doll',
    state: 'queued',
    progress: 0,
    message: null,
    error: null,
    result: null,
    created: '2026-10-18T09:30:00Z',
    started: null,
    finished: null,
    ...overrides,
  };
}

class FakeSocket implements SocketLike {
  onmessage: SocketLike['onmessage'] = null;
  onclose: SocketLike['onclose'] = null;
  closed = false;

  send(update: Job): void {
    this.onmessage?.({ data: JSON.stringify(update) });
  }

  drop(code = 1006): void {
    this.onclose?.({ code });
  }

  close(): void {
    this.closed = true;
  }
}

function watching(start: Job, poll = vi.fn<(id: string) => Promise<Job>>()) {
  const socket = new FakeSocket();
  const connect = vi.fn(() => socket);
  const watch = new JobWatch(start, { connect, poll, wait: () => Promise.resolve() });
  const seen: Job[] = [];
  watch.onChange = (update) => seen.push(update);
  return { socket, connect, watch, seen, poll };
}

describe('watching a job', () => {
  it('follows its progress over the WebSocket until it finishes', async () => {
    const { socket, connect, watch, seen } = watching(job());
    expect(connect).toHaveBeenCalledWith('3f9c2a7d1b6e4c08');
    socket.send(job({ state: 'running', progress: 0.5, message: 'Painting 1 of 2' }));
    expect(describeJob(watch.job)).toBe('Painting 1 of 2 (50%)');
    const result = { doll: '/api/jobs/files/doll/wren.json' };
    socket.send(job({ state: 'succeeded', progress: 1, message: 'Painted', result }));
    expect((await watch.done).result).toEqual(result);
    expect(seen.map((j) => j.state)).toEqual(['running', 'succeeded']);
    expect(socket.closed).toBe(true);
  });

  it('polls when the WebSocket drops before the job finishes', async () => {
    const poll = vi
      .fn<(id: string) => Promise<Job>>()
      .mockRejectedValueOnce(new Error('restarting'))
      .mockResolvedValueOnce(job({ state: 'running', progress: 0.2 }))
      .mockResolvedValueOnce(job({ state: 'failed', error: 'FLUX ran out of memory' }));
    const { socket, watch } = watching(job(), poll);
    socket.drop();
    const done = await watch.done;
    expect(done.state).toBe('failed');
    expect(describeJob(done)).toBe('Failed: FLUX ran out of memory');
    expect(poll).toHaveBeenCalledTimes(3);
  });

  it('fails a job the server doesn’t know', async () => {
    const { socket, watch } = watching(job());
    socket.drop(UNKNOWN_JOB);
    expect((await watch.done).state).toBe('failed');
  });

  it('is done straight away for a job that has already finished', async () => {
    const { connect, watch } = watching(job({ state: 'cancelled' }));
    expect(connect).not.toHaveBeenCalled();
    expect(describeJob(await watch.done)).toBe('Cancelled');
  });

  it('ignores updates once stopped', () => {
    const { socket, watch, seen } = watching(job());
    watch.stop();
    socket.send(job({ state: 'running' }));
    socket.drop();
    expect(seen).toEqual([]);
    expect(socket.closed).toBe(true);
  });

  it('says when a job is waiting its turn', () => {
    expect(describeJob(job())).toBe('Waiting for another job to finish');
  });
});
