import type { CreatureKind } from '../net';
import { hurts, type Hit, type Hurts } from '../ui/hurt';

/** What a hit sounds like: the creature that made it, or a thud when nothing did. */
export type HurtSound = CreatureKind | 'thud';
type Random = () => number;
type Voice = (t: number) => number;

export const HURT_GAIN = { least: 0.65, most: 1 };
const PEAK = 0.9;
const FADE_OUT_S = 0.006;

const TAU = 2 * Math.PI;
const decay = (t: number, seconds: number) => (t < 0 ? 0 : Math.exp(-t / seconds));
const ramp = (t: number, seconds: number) => Math.min(Math.max(t / seconds, 0), 1);

/** A one-pole low-pass, `hz` at `rate`. */
function lowPass(hz: number, rate: number): (x: number) => number {
  const a = 1 - Math.exp((-TAU * hz) / rate);
  let y = 0;
  return (x) => (y += a * (x - y));
}

/** A voice whose pitch follows `hz(t)`, its phase kept across the changes. */
function pitched(hz: (t: number) => number, rate: number, wave: (phase: number) => number): Voice {
  let phase = 0;
  return (t) => wave((phase += (TAU * hz(t)) / rate));
}

/** A band of noise from `low` to `high` Hz, falling off above it twice as steeply as below. */
function band(low: number, high: number, rate: number, random: Random): () => number {
  const under = [lowPass(high, rate), lowPass(high, rate)];
  const below = lowPass(low, rate);
  return () => {
    const x = under.reduce((y, pass) => pass(y), random() * 2 - 1);
    return x - below(x);
  };
}

const MAKERS: Record<HurtSound, { seconds: number; make: (rate: number, random: Random) => Voice }> = {
  thud: {
    seconds: 0.22,
    make: (rate, random) => {
      const body = pitched((t) => 45 + 75 * Math.exp(-t / 0.03), rate, Math.sin);
      const click = band(80, 900, rate, random);
      return (t) => body(t) * decay(t, 0.06) + 1.5 * click() * decay(t, 0.008);
    },
  },
  rat: {
    seconds: 0.34,
    make: (rate, random) => {
      const squeak = (from: number, to: number) => (t: number) => from + (to - from) * (1 - Math.exp(-t / 0.02)) + 120 * Math.sin(TAU * 28 * t);
      const chirp = pitched(squeak(2400, 3000), rate, (p) => Math.sin(p) + 0.2 * Math.sin(2 * p));
      const rising = squeak(2200, 3400);
      const eeek = pitched((t) => rising(t - 0.09) - 600 * ramp(t - 0.24, 0.1), rate, (p) => Math.sin(p) + 0.25 * Math.sin(2 * p) + 0.1 * Math.sin(3 * p));
      const breath = band(2000, 6000, rate, random);
      return (t) => {
        const first = t < 0.07 ? chirp(t) * ramp(t, 0.006) * (1 - ramp(t - 0.05, 0.02)) : 0;
        const second = t >= 0.09 ? eeek(t) * ramp(t - 0.09, 0.008) * (1 - ramp(t - 0.27, 0.07)) : 0;
        return 0.8 * first + second + 0.08 * breath() * (first || second ? 1 : 0);
      };
    },
  },
  bat: {
    seconds: 0.36,
    make: (rate, random) => {
      const carrier = pitched((t) => 3600 - 1400 * t + 800 * Math.sin(TAU * 95 * t), rate, Math.sin);
      const hiss = band(3000, 9000, rate, random);
      return (t) => {
        const flutter = 0.55 + 0.45 * Math.tanh(4 * Math.sin(TAU * 70 * t));
        const screech = Math.tanh(1.6 * (carrier(t) + 0.35 * hiss())) * flutter;
        return screech * ramp(t, 0.005) * decay(t, 0.14);
      };
    },
  },
  dog: {
    seconds: 0.56,
    make: (rate, random) => {
      const growl = band(120, 700, rate, random);
      const voice = pitched(
        (t) => 115 + 18 * Math.sin(TAU * 3 * t),
        rate,
        (p) => [1, 2, 3, 4, 5, 6].reduce((sum, k) => sum + Math.sin(k * p) / k ** 1.3, 0),
      );
      const crack = band(1500, 8000, rate, random);
      const jaw = pitched(() => 160, rate, Math.sin);
      return (t) => {
        const rasp = 0.5 + 0.5 * Math.tanh(4 * Math.sin(TAU * 32 * t));
        const snarl = (2 * growl() + 0.6 * voice(t)) * rasp * ramp(t, 0.05) * (1 - ramp(t - 0.33, 0.06));
        const snap = 2.2 * crack() * (decay(t - 0.4, 0.006) + 0.6 * decay(t - 0.425, 0.005)) + 0.8 * jaw(t) * decay(t - 0.4, 0.03);
        return snarl + snap;
      };
    },
  },
  bot: {
    seconds: 0.72,
    make: (rate, random) => {
      const partials = [
        [523, 1, 0.25],
        [529, 0.5, 0.22],
        [1307, 0.7, 0.18],
        [1977, 0.55, 0.14],
        [2741, 0.45, 0.1],
        [3602, 0.35, 0.08],
        [4890, 0.25, 0.05],
      ].map(([hz, level, seconds]) => ({ voice: pitched(() => hz, rate, Math.sin), level, seconds }));
      const strike = band(400, 8000, rate, random);
      const motor = pitched(
        (t) => 200 + 300 * Math.sin(Math.PI * ramp(t - 0.12, 0.6)),
        rate,
        (p) => Math.tanh(3 * Math.sin(p)) * 0.5 + 0.2 * Math.sin(2 * p),
      );
      const muffle = lowPass(2000, rate);
      return (t) => {
        const clank = partials.reduce((sum, { voice, level, seconds }) => sum + level * voice(t) * decay(t, seconds), 0) / 2;
        const whirring = t > 0.12 ? Math.sin(Math.PI * ramp(t - 0.12, 0.6)) ** 0.7 : 0;
        const whirr = muffle(motor(t) * (0.7 + 0.3 * Math.sin(TAU * 50 * t))) * whirring;
        return clank + 1.5 * strike() * decay(t, 0.004) + 0.45 * whirr;
      };
    },
  },
};

export const soundOf = (kind: CreatureKind | undefined): HurtSound => (kind && kind in MAKERS ? kind : 'thud');

export const secondsOf = (sound: HurtSound): number => MAKERS[sound].seconds;

/** `sound`, synthesized afresh, louder the harder the hit. */
export function hurtSamples(sound: HurtSound, strength: number, rate: number, random: Random = Math.random): Float32Array<ArrayBuffer> {
  const { seconds, make } = MAKERS[sound];
  const voice = make(rate, random);
  const samples = new Float32Array(Math.round(seconds * rate));
  let peak = 0;
  for (let i = 0; i < samples.length; i++) {
    const t = i / rate;
    samples[i] = voice(t) * Math.min((seconds - t) / FADE_OUT_S, 1);
    peak = Math.max(peak, Math.abs(samples[i]));
  }
  const gain = (PEAK * (HURT_GAIN.least + (HURT_GAIN.most - HURT_GAIN.least) * strength)) / (peak || 1);
  for (let i = 0; i < samples.length; i++) samples[i] *= gain;
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

/** Plays what hit the player, by `attacker`, every time they take damage, once the page may play audio. */
export function playHurts(
  output: SoundOutput,
  canPlay: () => boolean,
  attacker: () => CreatureKind | undefined,
  source: Pick<Hurts, 'on'> = hurts,
): () => void {
  return source.on(({ strength }: Hit) => {
    if (canPlay()) output.play(hurtSamples(soundOf(attacker()), strength, output.sampleRate));
  });
}
