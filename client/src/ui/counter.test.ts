// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Position } from '../net';
import type { Interactable } from '../world/interactables';
import { counterOf, CounterPrompt, servingAt } from './counter';
import { PLAYER_ID, type WorldView } from './world-view';

const counter: Interactable = {
  id: 'coffee_shop_counter',
  kind: 'counter',
  label: 'Counter',
  map: 'coffee_shop',
  stand: [{ x: 5, y: 6 }],
  prompt: 'Order at the counter',
};
const inside = (x: number, y: number): Position => ({ x, y, map: 'coffee_shop' });

function viewOf(positions: Record<string, Position>): WorldView {
  return {
    positionOf: (id) => positions[id],
    npcIds: () => Object.keys(positions).filter((id) => id !== PLAYER_ID),
    bubbleAnchor: () => undefined,
    spriteOf: () => undefined,
  };
}

describe('servingAt', () => {
  it('finds whoever is behind the counter, not the queue in front of it', () => {
    const view = viewOf({
      [PLAYER_ID]: inside(5, 6),
      ana: inside(5, 7),
      mirela: inside(5, 4),
      ben: inside(12, 9),
    });
    expect(servingAt(counter, view)).toBe('mirela');
  });

  it('finds them at the machine or handing a drink over too', () => {
    expect(servingAt(counter, viewOf({ mirela: inside(7, 3) }))).toBe('mirela');
    expect(servingAt(counter, viewOf({ mirela: inside(8, 4) }))).toBe('mirela');
  });

  it('finds nobody when nobody is behind it', () => {
    expect(servingAt(counter, viewOf({ ana: inside(5, 7), ben: inside(14, 3) }))).toBeUndefined();
    expect(servingAt(counter, viewOf({ mirela: { x: 5, y: 4, map: 'village' } }))).toBeUndefined();
  });
});

describe('CounterPrompt', () => {
  afterEach(() => vi.useRealTimers());

  it('prompts the player at a counter to order', () => {
    const prompt = new CounterPrompt(document.body);
    const hint = document.body.querySelector<HTMLElement>('.counter-hint')!;

    prompt.update(counter, true);
    expect(hint.hidden).toBe(false);
    expect(hint.textContent).toBe('Press E to order at the counter.');

    prompt.update(counter, false);
    expect(hint.hidden).toBe(true);
    prompt.update(undefined, true);
    expect(hint.hidden).toBe(true);
  });

  it('flashes a message for a moment', () => {
    vi.useFakeTimers();
    const prompt = new CounterPrompt(document.body);
    const hint = [...document.body.querySelectorAll<HTMLElement>('.counter-hint')].at(-1)!;

    prompt.flash("Nobody's behind the counter.");
    prompt.update(undefined, true);
    expect(hint.hidden).toBe(false);
    expect(hint.textContent).toBe("Nobody's behind the counter.");

    vi.advanceTimersByTime(3000);
    prompt.update(undefined, true);
    expect(hint.hidden).toBe(true);
  });
});

describe('counterOf', () => {
  it('is only for counters', () => {
    const painting: Interactable = { ...counter, kind: 'painting', prompt: 'Look at the painting' };
    expect(counterOf(counter)).toBe(counter);
    expect(counterOf(painting)).toBeUndefined();
    expect(counterOf(undefined)).toBeUndefined();
  });
});
