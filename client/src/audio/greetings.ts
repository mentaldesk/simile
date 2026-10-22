import type { PositionProvider } from './positions';
import { partnerMix, UNPOSITIONED, type Mix } from './spatial';

/** Seconds before the same resident's greeting plays again. */
export const GREETING_COOLDOWN_S = 60;

/** Plays a greeting's file: `WebGreetings` in the browser, a fake in tests. */
export type GreetingOutput = {
  play(url: string, mix: Mix): void;
};

/** The URLs of a resident's greetings, empty if they have none. */
export type GreetingList = (npcId: string) => Promise<readonly string[]>;

export type GreeterOptions = {
  cooldown?: number;
  /** Seconds, on any clock. */
  now?: () => number;
  random?: () => number;
  canPlay?: () => boolean;
};

/** Plays one of a resident's recorded greetings as they start talking to the player. */
export class Greeter {
  private readonly output: GreetingOutput;
  private readonly positions: PositionProvider;
  private readonly list: GreetingList;
  private readonly cooldown: number;
  private readonly now: () => number;
  private readonly random: () => number;
  private readonly canPlay: () => boolean;
  private readonly lists = new Map<string, Promise<readonly string[]>>();
  private readonly greeted = new Map<string, number>();

  constructor(
    output: GreetingOutput,
    positions: PositionProvider,
    list: GreetingList,
    options: GreeterOptions = {},
  ) {
    this.output = output;
    this.positions = positions;
    this.list = list;
    this.cooldown = options.cooldown ?? GREETING_COOLDOWN_S;
    this.now = options.now ?? (() => performance.now() / 1000);
    this.random = options.random ?? Math.random;
    this.canPlay = options.canPlay ?? (() => true);
  }

  /** Plays one at random, unless this resident's last one was within the cooldown. */
  async greet(npcId: string): Promise<boolean> {
    if (!this.canPlay()) return false;
    const now = this.now();
    const last = this.greeted.get(npcId);
    if (last !== undefined && now - last < this.cooldown) return false;
    this.greeted.set(npcId, now);
    const urls = await this.greetingsOf(npcId);
    if (!urls.length) return false;
    const url = urls[Math.min(urls.length - 1, Math.floor(this.random() * urls.length))];
    this.output.play(url, this.mixOf(npcId));
    return true;
  }

  private greetingsOf(npcId: string): Promise<readonly string[]> {
    let urls = this.lists.get(npcId);
    if (!urls) {
      urls = this.list(npcId).catch(() => {
        this.lists.delete(npcId);
        return [];
      });
      this.lists.set(npcId, urls);
    }
    return urls;
  }

  /** As loud as the player's partner, panned towards them. */
  private mixOf(npcId: string): Mix {
    const listener = this.positions.listenerPosition();
    const speaker = this.positions.positionOf(npcId);
    return listener && speaker ? partnerMix(listener, speaker) : UNPOSITIONED;
  }
}

/** The server's list of a resident's greetings. */
export async function fetchGreetings(npcId: string): Promise<readonly string[]> {
  const response = await fetch(`/api/greetings/${encodeURIComponent(npcId)}`);
  if (!response.ok) throw new Error(`greetings for ${npcId}: ${response.status}`);
  const { greetings } = (await response.json()) as { greetings: string[] };
  return greetings;
}

/** Fetches and decodes each greeting once, then plays it through its own gain and panner. */
export class WebGreetings implements GreetingOutput {
  private readonly context: BaseAudioContext;
  private readonly buffers = new Map<string, Promise<AudioBuffer>>();

  constructor(context: BaseAudioContext) {
    this.context = context;
  }

  play(url: string, { gain, pan }: Mix): void {
    this.buffer(url).then(
      (buffer) => {
        const source = new AudioBufferSourceNode(this.context, { buffer });
        const level = new GainNode(this.context, { gain });
        const panner = new StereoPannerNode(this.context, { pan });
        source.connect(level).connect(panner).connect(this.context.destination);
        source.onended = () => panner.disconnect();
        source.start();
      },
      () => this.buffers.delete(url),
    );
  }

  private buffer(url: string): Promise<AudioBuffer> {
    let buffer = this.buffers.get(url);
    if (!buffer) {
      buffer = fetch(url)
        .then((response) => response.arrayBuffer())
        .then((data) => this.context.decodeAudioData(data));
      this.buffers.set(url, buffer);
    }
    return buffer;
  }
}
