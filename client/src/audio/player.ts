import type { AudioChunk, Line, server } from '../net';
import { toFloat32 } from './pcm';
import type { PositionProvider } from './positions';
import { spatialMix, UNPOSITIONED, type Mix } from './spatial';
import { Timeline } from './timeline';

/** The Web Audio seam: webaudio.ts in the browser, a fake in tests. Times are in seconds. */
export type AudioOutput = {
  readonly now: number;
  createVoice(): VoiceOutput;
};

export type VoiceOutput = {
  play(samples: Float32Array<ArrayBuffer>, at: number): void;
  mix(mix: Mix): void;
  close(): void;
};

const STALE_S = 5;
export const REMEMBERED_LINES = 512;

type Voice = {
  output: VoiceOutput;
  timeline: Timeline;
  speaker?: string;
  mix?: Mix;
  heard: number;
  finished: boolean;
};

export class VoicePlayer {
  underruns = 0;
  private readonly output: AudioOutput;
  private readonly positions: PositionProvider;
  private readonly speakers = new Map<number, string>();
  private readonly voices = new Map<number, Voice>();

  constructor(output: AudioOutput, positions: PositionProvider) {
    this.output = output;
    this.positions = positions;
  }

  learn(line: Pick<Line, 'id' | 'speaker'>): void {
    this.speakers.delete(line.id);
    this.speakers.set(line.id, line.speaker);
    if (this.speakers.size > REMEMBERED_LINES) {
      const [oldest] = this.speakers.keys();
      this.speakers.delete(oldest);
    }
    const voice = this.voices.get(line.id);
    if (voice) {
      voice.speaker = line.speaker;
      this.position(voice);
    }
  }

  receive({ lineId, samples, last }: AudioChunk): void {
    const now = this.output.now;
    let voice = this.voices.get(lineId);
    if (!voice) {
      voice = {
        output: this.output.createVoice(),
        timeline: new Timeline(),
        speaker: this.speakers.get(lineId),
        heard: now,
        finished: false,
      };
      this.voices.set(lineId, voice);
      this.position(voice);
    }
    voice.heard = now;
    if (samples.length) {
      const { at, late } = voice.timeline.place(now, samples.length);
      if (late) this.underruns++;
      voice.output.play(toFloat32(samples), at);
    }
    if (last) {
      voice.finished = true;
      this.speakers.delete(lineId);
    }
  }

  /** Call it every frame. */
  update(): void {
    const now = this.output.now;
    for (const [lineId, voice] of this.voices) {
      const end = voice.timeline.end;
      const done = voice.finished ? now >= end : now >= Math.max(end, voice.heard) + STALE_S;
      if (done) {
        voice.output.close();
        this.voices.delete(lineId);
      } else {
        this.position(voice);
      }
    }
  }

  private position(voice: Voice): void {
    const listener = this.positions.listenerPosition();
    const source =
      voice.speaker === undefined ? undefined : this.positions.positionOf(voice.speaker);
    const mix = listener && source ? spatialMix(listener, source) : UNPOSITIONED;
    if (voice.mix?.gain === mix.gain && voice.mix.pan === mix.pan) return;
    voice.mix = mix;
    voice.output.mix(mix);
  }
}

export function listen(
  connection: Pick<typeof server, 'on'>,
  player: VoicePlayer,
  canPlay: () => boolean,
): () => void {
  const learnAll = (lines: Line[]) => lines.forEach((line) => player.learn(line));
  const unsubscribes = [
    connection.on('snapshot', ({ conversations }) =>
      conversations.forEach((conversation) => learnAll(conversation.lines)),
    ),
    connection.on('conversation_started', ({ conversation }) => learnAll(conversation.lines)),
    connection.on('line', ({ line }) => player.learn(line)),
    connection.on('audio_chunk', (chunk) => {
      if (canPlay()) player.receive(chunk);
    }),
  ];
  return () => unsubscribes.forEach((unsubscribe) => unsubscribe());
}
