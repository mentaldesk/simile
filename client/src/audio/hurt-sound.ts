import { hurts, type Hit, type Hurts } from '../ui/hurt';

/** Seconds long, and loudness from 0 to 1, for the weakest hit and the strongest. */
export const HURT_SECONDS = { least: 0.2, most: 0.38 };
export const HURT_GAIN = { least: 0.35, most: 0.8 };
const FADE_OUT_S = 0.006;

const lerp = (range: { least: number; most: number }, t: number) => range.least + (range.most - range.least) * t;

/**
 * A hit, synthesized: a thump dropping in pitch, a crack of noise and a short falling yelp, bigger,
 * lower and longer the harder it was.
 */
export function hurtSamples(strength: number, sampleRate: number, random: () => number = Math.random): Float32Array<ArrayBuffer> {
  const seconds = lerp(HURT_SECONDS, strength);
  const samples = new Float32Array(Math.round(seconds * sampleRate));
  const gain = lerp(HURT_GAIN, strength);
  const thump = { from: 170 - 40 * strength, to: 48 };
  const yelp = { from: 700 - 120 * strength, to: 240 };
  let thumpPhase = 0;
  let yelpPhase = 0;
  let noise = 0;
  for (let i = 0; i < samples.length; i++) {
    const t = i / sampleRate;
    thumpPhase += (2 * Math.PI * (thump.to + (thump.from - thump.to) * Math.exp(-t / 0.05))) / sampleRate;
    yelpPhase += (2 * Math.PI * (yelp.to + (yelp.from - yelp.to) * Math.exp(-t / 0.09))) / sampleRate;
    noise += 0.35 * (random() * 2 - 1 - noise);
    const body = Math.sin(thumpPhase) * Math.exp(-t / (0.07 + 0.05 * strength));
    const crack = noise * 1.6 * Math.exp(-t / 0.025);
    const cry = Math.tanh(3 * Math.sin(yelpPhase)) * Math.min(t / 0.01, 1) * Math.exp(-t / (0.06 + 0.04 * strength));
    const fade = Math.min((seconds - t) / FADE_OUT_S, 1);
    samples[i] = Math.tanh(0.8 * body + crack + 0.3 * cry) * gain * fade;
  }
  return samples;
}

/** Plays a mono sound once, centred: `webSound` in the browser, a fake in tests. */
export type SoundOutput = { readonly sampleRate: number; play(samples: Float32Array<ArrayBuffer>): void };

export function webSound(context: BaseAudioContext): SoundOutput {
  return {
    sampleRate: context.sampleRate,
    play(samples) {
      const buffer = new AudioBuffer({ length: samples.length, sampleRate: context.sampleRate });
      buffer.copyToChannel(samples, 0);
      const source = new AudioBufferSourceNode(context, { buffer });
      source.connect(context.destination);
      source.onended = () => source.disconnect();
      source.start();
    },
  };
}

/** Plays a hit every time the player takes damage, once the page may play audio. */
export function playHurts(output: SoundOutput, canPlay: () => boolean, source: Pick<Hurts, 'on'> = hurts): () => void {
  return source.on(({ strength }: Hit) => {
    if (canPlay()) output.play(hurtSamples(strength, output.sampleRate));
  });
}
