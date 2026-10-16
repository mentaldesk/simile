import type { AudioChunk, Conversation, Line, server } from '../net';
import { PLAYER_ID } from '../ui/world-view';
import { toFloat32 } from './pcm';
import type { PositionProvider } from './positions';
import { overheardMix, partnerMix, UNPOSITIONED, type Mix } from './spatial';
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

type Speaker = { id: string; partner: boolean };

type Voice = {
  output: VoiceOutput;
  timeline: Timeline;
  speaker?: Speaker;
  mix?: Mix;
  heard: number;
  finished: boolean;
};

export class VoicePlayer {
  underruns = 0;
  private readonly output: AudioOutput;
  private readonly positions: PositionProvider;
  private readonly speakers = new Map<number, Speaker>();
  private readonly voices = new Map<number, Voice>();

  constructor(output: AudioOutput, positions: PositionProvider) {
    this.output = output;
    this.positions = positions;
  }

  learn(line: Pick<Line, 'id' | 'speaker'>, partner = false): void {
    const speaker = { id: line.speaker, partner };
    this.speakers.delete(line.id);
    this.speakers.set(line.id, speaker);
    if (this.speakers.size > REMEMBERED_LINES) {
      const [oldest] = this.speakers.keys();
      this.speakers.delete(oldest);
    }
    const voice = this.voices.get(line.id);
    if (voice) {
      voice.speaker = speaker;
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
    const { speaker } = voice;
    const source = speaker && this.positions.positionOf(speaker.id);
    const mixOf = speaker?.partner ? partnerMix : overheardMix;
    const mix = listener && source ? mixOf(listener, source) : UNPOSITIONED;
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
  const withPlayer = new Set<string>();
  const learn = (line: Line) => player.learn(line, withPlayer.has(line.conversation_id));
  const follow = ({ id, participants, lines }: Conversation) => {
    if (participants.includes(PLAYER_ID)) withPlayer.add(id);
    lines.forEach(learn);
  };
  const unsubscribes = [
    connection.on('snapshot', ({ conversations }) => {
      withPlayer.clear();
      conversations.forEach(follow);
    }),
    connection.on('conversation_started', ({ conversation }) => follow(conversation)),
    connection.on('conversation_ended', ({ conversation_id: id }) => withPlayer.delete(id)),
    connection.on('line', ({ line }) => learn(line)),
    connection.on('audio_chunk', (chunk) => {
      if (canPlay()) player.receive(chunk);
    }),
  ];
  return () => unsubscribes.forEach((unsubscribe) => unsubscribe());
}
