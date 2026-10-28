// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Position } from '../net';
import type { Interactable } from '../world/interactables';
import { CounterPrompt, servingAt } from './counter';
import { PLAYER_ID, type WorldView } from './world-view';

/** content/street/floors/coffee_shop_floor_0.tmj's: the counter along 3 to 5, ordered at from 6. */
const counter: Interactable = {
  id: 'coffee_shop_counter',
  kind: 'counter',
  label: 'Counter',
  map: 'coffee_shop_floor_0',
  area: { x: 3, y: 2, width: 3, height: 1 },
  stand: [{ x: 6, y: 2 }],
  prompt: 'Order at the counter',
};
const inside = (x: number, y = 2): Position => ({ x, y, map: 'coffee_shop_floor_0' });

function viewOf(positions: Record<string, Position>): WorldView {
  return {
    positionOf: (id) => positions[id],
    npcIds: () => Object.keys(positions).filter((id) => id !== PLAYER_ID),
    bubbleAnchor: () => undefined,
    spriteOf: () => undefined,
  };
}

describe('servingAt', () => {
  it('finds whoever is behind the counter along its row, not the queue or the pickup', () => {
    const view = viewOf({
      [PLAYER_ID]: inside(6),
      ana: inside(7),
      ben: inside(5),
      mirela: inside(3),
      tom: inside(12),
    });
    expect(servingAt(counter, view)).toBe('mirela');
  });

  it('finds them at the grinder, the machine or handing a drink over too', () => {
    for (const x of [1, 2, 4]) expect(servingAt(counter, viewOf({ mirela: inside(x) }))).toBe('mirela');
  });

  it('finds the one nearest the stand', () => {
    expect(servingAt(counter, viewOf({ mirela: inside(1), odalys: inside(4) }))).toBe('odalys');
  });

  it('finds nobody when nobody is behind it', () => {
    expect(servingAt(counter, viewOf({ ana: inside(7), ben: inside(5), tom: inside(14) }))).toBeUndefined();
    expect(servingAt(counter, viewOf({ mirela: inside(3, 0) }))).toBeUndefined();
    expect(servingAt(counter, viewOf({ mirela: { x: 3, y: 2, map: 'coffee_shop_floor_1' } }))).toBeUndefined();
  });

  it('works the same way round with the stand at the counter’s other end', () => {
    const mirrored = { ...counter, area: { x: 10, y: 2, width: 3, height: 1 }, stand: [{ x: 9, y: 2 }] };
    expect(servingAt(mirrored, viewOf({ ben: inside(10), mirela: inside(12) }))).toBe('mirela');
    expect(servingAt(mirrored, viewOf({ mirela: inside(15) }))).toBeUndefined();
  });
});

describe('CounterPrompt', () => {
  afterEach(() => vi.useRealTimers());

  it('prompts the player at a counter to order with T, and at a jack to use it with E', () => {
    const prompt = new CounterPrompt(document.body);
    const hint = document.body.querySelector<HTMLElement>('.counter-hint')!;

    prompt.update({ ...counter, kind: 'jack', prompt: 'Use the dead terminal' }, true);
    expect(hint.textContent).toBe('Press E to use the dead terminal.');
    prompt.update(counter, true);
    expect(hint.hidden).toBe(false);
    expect(hint.textContent).toBe('Press T to order at the counter.');

    prompt.update(counter, false);
    expect(hint.hidden).toBe(true);
    prompt.update(undefined, true);
    expect(hint.hidden).toBe(true);
  });

  it('flashes a message for a moment', () => {
    vi.useFakeTimers();
    const prompt = new CounterPrompt(document.body);
    const hint = [...document.body.querySelectorAll<HTMLElement>('.counter-hint')].at(-1)!;

    prompt.flash('Nothing happens: the dead terminal needs a datajack.');
    prompt.update(undefined, true);
    expect(hint.hidden).toBe(false);
    expect(hint.textContent).toBe('Nothing happens: the dead terminal needs a datajack.');

    vi.advanceTimersByTime(3000);
    prompt.update(undefined, true);
    expect(hint.hidden).toBe(true);
  });
});
