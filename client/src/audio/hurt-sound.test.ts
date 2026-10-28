import { describe, expect, it } from 'vitest';
import type { CreatureKind } from '../net';
import { ServerConnection } from '../net/connection';
import { Hurts } from '../ui/hurt';
import { HURT_GAIN, hurtSamples, playHurts, secondsOf, soundOf, type HurtSound } from './hurt-sound';

const RATE = 24_000;
const steady = () => 0.5;
const peak = (samples: Float32Array) => samples.reduce((most, sample) => Math.max(most, Math.abs(sample)), 0);
/** Sign changes a second: a rough pitch. */
const crossings = (samples: Float32Array) => {
  let count = 0;
  for (let i = 1; i < samples.length; i++) if (samples[i - 1] < 0 !== samples[i] < 0) count++;
  return (count * RATE) / samples.length;
};

describe('the sound of a hit', () => {
  it('is the attacker’s: a high squeak or screech for a rat or a bat, low for a dog or a thud', () => {
    const pitch = (sound: HurtSound) => crossings(hurtSamples(sound, 1, RATE, steady));
    expect(pitch('rat')).toBeGreaterThan(4000);
    expect(pitch('bat')).toBeGreaterThan(4000);
    expect(pitch('thud')).toBeLessThan(1000);
    expect(pitch('dog')).toBeLessThan(pitch('rat'));
    expect(soundOf('dog')).toBe('dog');
    expect(soundOf(undefined)).toBe('thud');
  });

  it('is a little louder the harder the hit, and ends quietly', () => {
    for (const sound of ['rat', 'bot', 'dog', 'bat', 'thud'] as const) {
      const bat = hurtSamples(sound, 0.3, RATE, steady);
      const bot = hurtSamples(sound, 1, RATE, steady);
      expect(bot.length).toBe(Math.round(secondsOf(sound) * RATE));
      expect(peak(bot)).toBeCloseTo(0.9 * HURT_GAIN.most);
      expect(peak(bat)).toBeLessThan(peak(bot));
      expect(peak(bat)).toBeGreaterThan(0.9 * HURT_GAIN.least * 0.99);
      expect(Math.abs(bot.at(-1)!)).toBeLessThan(0.01);
    }
  });

  it('plays what hit them on a health drop, a thud with nothing near, and nothing on healing or before the page may play', () => {
    const connection = new ServerConnection();
    const played: number[] = [];
    let canPlay = true;
    let attacker: CreatureKind | undefined = 'rat';
    playHurts({ sampleRate: RATE, play: (samples) => played.push(samples.length) }, () => canPlay, () => attacker, new Hurts(connection));
    const health = (health: number) => connection.dispatch(JSON.stringify({ type: 'player_state', player: { health } }));
    health(1);
    health(0.95);
    attacker = 'bot';
    health(0.85);
    attacker = undefined;
    health(0.8);
    health(1);
    canPlay = false;
    health(0.9);
    const lengths = (['rat', 'bot', 'thud'] as const).map((sound) => Math.round(secondsOf(sound) * RATE));
    expect(played).toEqual(lengths);
  });
});
