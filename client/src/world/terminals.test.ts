import { describe, expect, it } from 'vitest';
import { village } from './assets';
import { entryOf } from './map';
import { terminalAt, terminalsOf } from './terminals';

const terminals = terminalsOf(village);

describe('terminals', () => {
  it('are the map’s terminal locations, in tiles', () => {
    expect(terminals.map(({ id }) => id)).toEqual(['terminal_1', 'terminal_2', 'terminal_3']);
    expect(terminals[0]).toEqual({
      id: 'terminal_1',
      label: 'News terminal on the square',
      x: 36,
      y: 13,
      width: 1,
      height: 3,
    });
  });

  it('are in reach from their entry and the tiles next to them', () => {
    const entry = entryOf(village, 'terminal_2')!;
    expect(terminalAt(terminals, entry)?.id).toBe('terminal_2');
    expect(terminalAt(terminals, { x: 36.4, y: 15.4 })?.id).toBe('terminal_1');
    expect(terminalAt(terminals, { x: 35, y: 12 })?.id).toBe('terminal_1');
    expect(terminalAt(terminals, { x: 37.4, y: 16.4 })?.id).toBe('terminal_1');
  });

  it('are out of reach two tiles away, and from nowhere', () => {
    expect(terminalAt(terminals, { x: 34, y: 14 })).toBeUndefined();
    expect(terminalAt(terminals, { x: 36, y: 17.5 })).toBeUndefined();
    expect(terminalAt(terminals, entryOf(village, 'square'))).toBeUndefined();
    expect(terminalAt(terminals, undefined)).toBeUndefined();
  });
});
