import { SAMPLE_RATE } from '../../net';
import { decodeAudioChunk } from '../../net/audio';
import { VoicePlayer } from '../player';
import { JITTER_BUFFER_S } from '../timeline';
import { WebAudioOutput } from '../webaudio';
import { arrivalGaps, audioFrames } from './stream';

const RENDER_QUANTUM = 128;
const PAN_CENTRE_GAIN = Math.SQRT1_2;

export type GaplessCheck = { seconds: number; worstError: number; underruns: number };

/** Streams a line unevenly through the real pipeline, offline, and compares output with input. */
export async function checkGapless(samples: Int16Array): Promise<GaplessCheck> {
  const context = new OfflineAudioContext({
    numberOfChannels: 2,
    length: samples.length + SAMPLE_RATE,
    sampleRate: SAMPLE_RATE,
  });
  const here = { x: 0, y: 0 };
  const player = new VoicePlayer(new WebAudioOutput(context), {
    positionOf: () => here,
    listenerPosition: () => here,
  });
  const [first, ...rest] = audioFrames(1, samples).map(decodeAudioChunk);
  player.receive(first);
  let arrival = 0;
  arrivalGaps(rest.length).forEach((gap, i) => {
    arrival += gap;
    const quantum = Math.ceil((arrival * SAMPLE_RATE) / RENDER_QUANTUM);
    void context.suspend((quantum * RENDER_QUANTUM) / SAMPLE_RATE).then(() => {
      player.receive(rest[i]);
      void context.resume();
    });
  });
  const rendered = (await context.startRendering()).getChannelData(0);

  const start = Math.round(JITTER_BUFFER_S * SAMPLE_RATE);
  const gainSettled = start + SAMPLE_RATE / 2;
  let worstError = 0;
  rendered.forEach((actual, i) => {
    if (i >= start && i < gainSettled) return;
    const source = samples[i - start] ?? 0;
    worstError = Math.max(worstError, Math.abs(actual - (PAN_CENTRE_GAIN * source) / 32768));
  });
  return { seconds: samples.length / SAMPLE_RATE, worstError, underruns: player.underruns };
}
