export type JobState = 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled';

export type Job = {
  id: string;
  kind: string;
  state: JobState;
  progress: number;
  message: string | null;
  error: string | null;
  result: Record<string, unknown> | null;
  created: string;
  started: string | null;
  finished: string | null;
};

export interface SocketLike {
  onmessage: ((event: { data: unknown }) => void) | null;
  onclose: ((event: { code: number }) => void) | null;
  close(): void;
}

export const UNKNOWN_JOB = 4404;
const POLL_MS = 1000;

export function finished(job: Job): boolean {
  return job.state === 'succeeded' || job.state === 'failed' || job.state === 'cancelled';
}

type Options = {
  connect: (id: string) => SocketLike;
  poll: (id: string) => Promise<Job>;
  wait?: (ms: number) => Promise<void>;
};

export class JobWatch {
  job: Job;
  onChange: (job: Job) => void = () => {};
  readonly done: Promise<Job>;
  private socket: SocketLike | null = null;
  private stopped = false;
  private settle!: (job: Job) => void;
  private readonly options: Required<Options>;

  constructor(job: Job, options: Options) {
    this.job = job;
    this.options = { wait: (ms) => new Promise((r) => setTimeout(r, ms)), ...options };
    this.done = new Promise((resolve) => (this.settle = resolve));
    if (finished(job)) {
      this.settle(job);
      return;
    }
    this.open();
  }

  stop(): void {
    this.stopped = true;
    this.socket?.close();
  }

  private open(): void {
    const socket = this.options.connect(this.job.id);
    this.socket = socket;
    socket.onmessage = ({ data }) => this.update(JSON.parse(String(data)) as Job);
    socket.onclose = ({ code }) => {
      this.socket = null;
      if (this.stopped || finished(this.job)) return;
      if (code === UNKNOWN_JOB) {
        this.update({ ...this.job, state: 'failed', error: 'The server no longer has this job' });
      } else {
        void this.pollUntilFinished();
      }
    };
  }

  private async pollUntilFinished(): Promise<void> {
    while (!this.stopped && !finished(this.job)) {
      await this.options.wait(POLL_MS);
      if (this.stopped) return;
      const polled = await this.options.poll(this.job.id).catch(() => null);
      if (polled) this.update(polled);
    }
  }

  private update(job: Job): void {
    if (this.stopped || finished(this.job)) return;
    this.job = job;
    this.onChange(job);
    if (finished(job)) {
      this.socket?.close();
      this.settle(job);
    }
  }
}

export function describe(job: Job): string {
  switch (job.state) {
    case 'queued':
      return 'Waiting for another job to finish';
    case 'running':
      return `${job.message ?? 'Working'} (${Math.round(job.progress * 100)}%)`;
    case 'succeeded':
      return job.message ?? 'Done';
    case 'failed':
      return `Failed: ${job.error ?? 'no reason given'}`;
    case 'cancelled':
      return 'Cancelled';
  }
}
