import { describe, expect, it } from 'vitest';
import { ServerConnection } from '../net/connection';
import { Hurts } from '../ui/hurt';
import { HURT_SECONDS, hurtSamples, playHurts } from './hurt-sound';

const RATE = 24_000;
const steady = () => 0.5;
const peak = (samples: Float32Array) => samples.reduce((most, sample) => Math.max(most, Math.abs(sample)), 0);

describe('the sound of a hit', () => {
  it('is louder and longer the harder the hit, and ends quietly', () => {
    const bat = hurtSamples(0.3, RATE, steady);
    const bot = hurtSamples(1, RATE, steady);
    expect(bot.length).toBe(HURT_SECONDS.most * RATE);
    expect(bat.length).toBeLessThan(bot.length);
    expect(peak(bat)).toBeLessThan(peak(bot));
    expect(peak(bot)).toBeLessThanOrEqual(1);
    expect(Math.abs(bot.at(-1)!)).toBeLessThan(0.01);
  });

  it('plays on a health drop, scaled by its size, and not on healing or before the page may play', () => {
    const connection = new ServerConnection();
    const played: Float32Array[] = [];
    let canPlay = true;
    playHurts({ sampleRate: RATE, play: (samples) => played.push(samples) }, () => canPlay, new Hurts(connection));
    const health = (health: number) => connection.dispatch(JSON.stringify({ type: 'player_state', player: { health } }));
    health(1);
    health(0.97);
    health(0.87);
    health(1);
    canPlay = false;
    health(0.9);
    expect(played).toHaveLength(2);
    expect(played[0].length).toBeLessThan(played[1].length);
  });
});
