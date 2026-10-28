// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { PlayerStateMessage } from '../net';
import { ServerConnection } from '../net/connection';
import { Fade, HealthGauge, PULSE_SECONDS } from './health-gauge';
import { Hurts } from './hurt';

const state = (health: number) => ({ type: 'player_state', player: { health } }) as PlayerStateMessage;

function gauge() {
  const connection = new ServerConnection();
  const corner = document.createElement('div');
  let now = 0;
  const health = new HealthGauge(corner, new Hurts(connection), () => now);
  const shown = corner.querySelector<HTMLElement>('.health-gauge')!;
  const at = (seconds: number, value: number) => {
    now = seconds;
    connection.dispatch(JSON.stringify(state(value)));
    health.update(state(value));
  };
  return {
    at,
    shown,
    pulse: () => Number(shown.style.getPropertyValue('--pulse')),
    lost: () => shown.querySelector<HTMLElement>('.health-lost')!.style.width,
  };
}

describe('a fade', () => {
  it('falls from its strength to nothing, keeping the stronger of two', () => {
    const fade = new Fade();
    fade.start(1, 0, 0.5);
    expect(fade.left(0)).toBe(1);
    expect(fade.left(0.25)).toBeCloseTo(0.5);
    expect(fade.left(0.5)).toBe(0);
    fade.start(0.2, 0.1, 0.5);
    expect(fade.left(0.1)).toBeCloseTo(0.8);
  });
});

describe('the health gauge', () => {
  it('heads the hunger corner while they are hurt, and pulses with what a hit took', () => {
    const { shown, at, lost } = gauge();
    at(0, 1);
    expect(shown.hidden).toBe(true);
    at(1, 0.9);
    expect(shown.hidden).toBe(false);
    expect(shown.classList).toContain('health-gauge-pulsing');
    expect(shown.ariaLabel).toBe('Health 90%');
    expect(lost()).toBe('100%');
    at(1 + PULSE_SECONDS, 0.9);
    expect(shown.classList).not.toContain('health-gauge-pulsing');
    expect(lost()).toBe('90%');
    at(2, 0.95);
    expect(shown.classList).not.toContain('health-gauge-pulsing');
    at(3, 1);
    expect(shown.hidden).toBe(true);
  });

  it('pulses harder for a bigger hit', () => {
    const { at, pulse } = gauge();
    at(0, 1);
    at(1, 0.97);
    const bat = pulse();
    at(5, 0.87);
    expect(pulse()).toBeGreaterThan(bat);
  });
});
