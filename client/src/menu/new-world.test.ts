import { describe, expect, it } from 'vitest';
import { NewWorldState } from './new-world';

const rival = (actor: string, target: string) => ({ kind: 'rival' as const, actor, target });

describe('NewWorldState', () => {
  it('starts with every house open', () => {
    const state = new NewWorldState(10);

    expect(state.count).toBe(10);
    expect(state.residents).toEqual([]);
    expect(state.open).toBe(10);
    expect(state.request()).toEqual({ count: 10, picks: [], pins: [] });
  });

  it('picks and unpicks', () => {
    const state = new NewWorldState(10, 6);

    for (const id of ['a', 'b', 'c']) state.toggle(id);
    state.toggle('b');

    expect(state.picks).toEqual(['a', 'c']);
    expect(state.isPicked('b')).toBe(false);
    expect(state.open).toBe(4);
    expect(state.request()).toEqual({ count: 6, picks: ['a', 'c'], pins: [] });
  });

  it('makes room for a pick by letting the last drawn resident go', () => {
    const state = new NewWorldState(10, 3);
    state.toggle('a');
    state.randomised(['a', 'x', 'y']);

    state.toggle('b');

    expect(state.residents).toEqual(['a', 'b', 'x']);
    expect(state.count).toBe(3);
  });

  it('grows the village for a pick when nobody was drawn, up to the houses', () => {
    const state = new NewWorldState(3, 2);
    state.toggle('a');
    state.toggle('b');

    expect(state.toggle('c')).toBe(true);
    expect(state.count).toBe(3);
    expect(state.toggle('d')).toBe(false);
    expect(state.residents).toEqual(['a', 'b', 'c']);
  });

  it('keeps the count between the picks and the houses', () => {
    const state = new NewWorldState(10, 6);
    state.toggle('a');
    state.toggle('b');
    state.randomised(['a', 'b', 'x', 'y', 'z']);

    state.setCount(3);
    expect(state.count).toBe(3);
    expect(state.residents).toEqual(['a', 'b', 'x']);

    state.setCount(0);
    expect(state.count).toBe(2);
    expect(state.residents).toEqual(['a', 'b']);

    state.setCount(12);
    expect(state.count).toBe(10);
  });

  it('asks for a draw that keeps the picks and the pins between them', () => {
    const state = new NewWorldState(10, 6);
    state.toggle('a');
    state.toggle('b');
    state.randomised(['a', 'b', 'x']);
    state.pin(rival('a', 'b'));
    state.pin(rival('a', 'x'));

    expect(state.drawRequest()).toEqual({ count: 6, picks: ['a', 'b'], pins: [rival('a', 'b')] });
  });

  it('replaces the last draw, and drops pins to anyone who left', () => {
    const state = new NewWorldState(10, 4);
    state.toggle('a');
    state.randomised(['a', 'x', 'y', 'z']);
    state.pin(rival('a', 'x'));
    state.pin(rival('y', 'z'));

    state.randomised(['a', 'p', 'y', 'z']);

    expect(state.picks).toEqual(['a']);
    expect(state.draws).toEqual(['p', 'y', 'z']);
    expect(state.isDrawn('x')).toBe(false);
    expect(state.pins).toEqual([rival('y', 'z')]);
  });

  it('pins a bond between two residents, once', () => {
    const state = new NewWorldState(10, 4);
    state.toggle('a');
    state.toggle('b');

    expect(state.pin(rival('a', 'a'))).toMatch('two different');
    expect(state.pin(rival('a', 'c'))).toMatch('Pick both');
    expect(state.pin({ kind: 'debt', actor: 'b', target: 'a' })).toBeNull();
    expect(state.pin(rival('a', 'b'))).toMatch('already have a bond');
    expect(state.request().pins).toEqual([{ kind: 'debt', actor: 'b', target: 'a' }]);
  });

  it('drops a resident’s pins when they leave', () => {
    const state = new NewWorldState(10, 4);
    for (const id of ['a', 'b', 'c']) state.toggle(id);
    state.pin(rival('a', 'b'));
    state.pin(rival('b', 'c'));
    state.pin(rival('a', 'c'));

    state.toggle('b');
    expect(state.pins).toEqual([rival('a', 'c')]);

    state.unpin(0);
    expect(state.pins).toEqual([]);
  });

  it('clears picks, draws and pins', () => {
    const state = new NewWorldState(10, 4);
    state.toggle('a');
    state.randomised(['a', 'x']);
    state.pin(rival('a', 'x'));

    state.clear();

    expect(state.request()).toEqual({ count: 4, picks: [], pins: [] });
  });
});
