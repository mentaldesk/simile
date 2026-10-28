// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { PlayerStateMessage } from '../net';
import { ServerConnection } from '../net/connection';
import { Hurts } from './hurt';
import { Fade, FLASH_OPACITY, FLASH_SECONDS, HurtView, PULSE_SECONDS } from './hurt-view';

const AFTER_BAT = FLASH_SECONDS.least + 0.15;
const state = (health: number) => ({ type: 'player_state', player: { health } }) as PlayerStateMessage;

/** A frame at `seconds`, after `player_state` with `health`. */
function view() {
  const connection = new ServerConnection();
  const parent = document.createElement('div');
  const corner = parent.appendChild(document.createElement('div'));
  let now = 0;
  const hurt = new HurtView(parent, corner, new Hurts(connection), () => now);
  const gauge = corner.querySelector<HTMLElement>('.health-gauge')!;
  const at = (seconds: number, health: number) => {
    now = seconds;
    connection.dispatch(JSON.stringify(state(health)));
    hurt.update(state(health));
  };
  return {
    at,
    flash: parent.querySelector<HTMLElement>('.hurt-flash')!,
    gauge,
    lost: () => gauge.querySelector<HTMLElement>('.health-lost')!.style.width,
  };
}

describe('the flash', () => {
  it('fades from a hit’s strength, keeping the stronger of two', () => {
    const fade = new Fade();
    fade.start(1, 0, 0.5);
    expect(fade.left(0)).toBe(1);
    expect(fade.left(0.25)).toBeCloseTo(0.5);
    expect(fade.left(0.5)).toBe(0);
    expect(fade.start(0.2, 0.1, 0.5)).toBe(false);
  });

  it('reddens the edges on a health drop, as strong and as long as the hit, and not on healing', () => {
    const { flash, at } = view();
    at(0, 1);
    expect(flash.hidden).toBe(true);
    at(1, 0.97);
    expect(flash.hidden).toBe(false);
    const bat = { opacity: Number(flash.style.opacity), shadow: flash.style.boxShadow };
    expect(bat.opacity).toBeGreaterThan(FLASH_OPACITY.least);
    at(1 + AFTER_BAT, 0.97);
    expect(flash.hidden).toBe(true);
    at(5, 0.87);
    expect(Number(flash.style.opacity)).toBeGreaterThan(bat.opacity);
    expect(flash.style.boxShadow).not.toBe(bat.shadow);
    at(5 + AFTER_BAT, 0.87);
    expect(flash.hidden).toBe(false);
    at(10, 1);
    expect(flash.hidden).toBe(true);
  });
});

describe('the health gauge', () => {
  it('heads the hunger corner while they are hurt, and pulses with what a hit took', () => {
    const { gauge, at, lost } = view();
    at(0, 1);
    expect(gauge.hidden).toBe(true);
    at(1, 0.9);
    expect(gauge.hidden).toBe(false);
    expect(gauge.classList).toContain('health-gauge-pulsing');
    expect(gauge.ariaLabel).toBe('Health 90%');
    expect(lost()).toBe('100%');
    at(1 + PULSE_SECONDS, 0.9);
    expect(gauge.classList).not.toContain('health-gauge-pulsing');
    expect(lost()).toBe('90%');
    at(2, 0.95);
    expect(gauge.classList).not.toContain('health-gauge-pulsing');
    at(3, 1);
    expect(gauge.hidden).toBe(true);
  });
});
