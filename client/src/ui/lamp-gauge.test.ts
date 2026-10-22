// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import type { Item, PlayerStateMessage } from '../net';
import { lampHint, LampGauge, level } from './lamp-gauge';

const lamp = (charge: number, on: boolean): Item => ({ id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge, on });
const LIT = { dark: false, plug: false };

function state(items: Item[]): PlayerStateMessage {
  const body = {
    legs: 'present',
    vertebra: 'present',
    left_eye: 'present',
    right_eye: 'present',
    left_kidney: 'present',
    right_kidney: 'present',
  } as const;
  return { type: 'player_state', player: { money: 0, items, carry_limit: 10, body, hunger: 0 } };
}

const shown = (root: HTMLElement, selector: string) => {
  const element = root.querySelector<HTMLElement>(selector)!;
  return element.hidden ? null : element.textContent;
};

describe('lampHint', () => {
  const lit = { dark: false, plug: false };
  const dark = { dark: true, plug: false };

  it('says nothing in the light with charge to spare', () => {
    expect(lampHint(lamp(0.8, false), lit)).toBeUndefined();
    expect(lampHint(lamp(0.8, true), lit)).toBeUndefined();
    expect(lampHint(undefined, dark)).toBeUndefined();
  });

  it('offers the lamp in the dark, and warns as it runs low or flat', () => {
    expect(lampHint(lamp(0.8, false), dark)).toBe("It's dark. Press L for your lamp.");
    expect(lampHint(lamp(0.8, true), dark)).toBeUndefined();
    expect(lampHint(lamp(0.15, true), dark)).toBe('Your lamp is running low.');
    expect(lampHint(lamp(0, false), dark)).toBe("It's dark, and your lamp is flat. Charge it at a plug.");
    expect(lampHint(lamp(0, false), lit)).toBe('Your lamp is flat. Charge it at a plug.');
  });

  it('says when it is charging at a plug, and when it is full', () => {
    expect(lampHint(lamp(0.3, false), { dark: false, plug: true })).toBe('Charging your lamp.');
    expect(lampHint(lamp(1, true), { dark: false, plug: true })).toBe('Your lamp is charged.');
  });

  it('colours the battery by what is left', () => {
    expect([1, 0.6, 0.5, 0.21, 0.2, 0].map(level)).toEqual(['full', 'full', 'half', 'half', 'low', 'low']);
  });
});

describe('LampGauge', () => {
  it('shows the battery and the switch, and hides without a lamp', () => {
    const root = document.createElement('div');
    const gauge = new LampGauge(root);

    gauge.update(state([lamp(0.64, true)]), LIT);
    const fill = root.querySelector<HTMLElement>('.lamp-battery > span')!;
    expect(shown(root, '.lamp-gauge')).toBe('Lon');
    expect(fill.style.width).toBe('64%');
    expect(fill.className).toBe('lamp-level-full');
    expect(root.querySelector('.lamp-gauge')!.ariaLabel).toBe('Lamp on, 64%');

    gauge.update(state([]), LIT);
    expect(shown(root, '.lamp-gauge')).toBeNull();
    expect(shown(root, '.lamp-hint')).toBeNull();
  });

  it('marks charging at a plug, and hints in the dark', () => {
    const root = document.createElement('div');
    const gauge = new LampGauge(root);

    gauge.update(state([lamp(0.1, false)]), { dark: false, plug: true });
    expect(shown(root, '.lamp-gauge')).toBe('L⚡');
    expect(shown(root, '.lamp-hint')).toBe('Charging your lamp.');
    expect(root.querySelector('.lamp-battery > span')!.className).toBe('lamp-level-low');

    gauge.update(state([lamp(0.5, false)]), { dark: true, plug: false });
    expect(shown(root, '.lamp-gauge')).toBe('Loff');
    expect(shown(root, '.lamp-hint')).toBe("It's dark. Press L for your lamp.");
  });
});
