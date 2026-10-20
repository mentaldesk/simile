import { describe, expect, it } from 'vitest';
import { maps } from './assets';
import { entryOf, type TiledMap } from './map';
import { terminalAt, terminalsOf, terminalsOn } from './terminals';

const terminals = terminalsOn(maps);
const street = (map: string, x: number, y = 15) => ({ x, y, map });

describe('terminals', () => {
  it('are every map’s terminal locations, in tiles', () => {
    expect(terminals.map(({ id, map }) => `${map}:${id}`).sort()).toEqual([
      'banyan_row:terminal_3',
      'high_street:terminal_1',
      'lychee_lane:terminal_2',
    ]);
    expect(terminalsOf(maps.high_street!, 'high_street')).toEqual([
      {
        id: 'terminal_1',
        label: 'News terminal on the square',
        map: 'high_street',
        x: 60,
        y: 13,
        width: 1,
        height: 3,
      },
    ]);
  });

  it('are in reach from their entry and the tiles either side', () => {
    for (const { id, map } of terminals) {
      const entry = entryOf(maps[map] as TiledMap, id)!;
      expect(terminalAt(terminals, { ...entry, map })?.id).toBe(id);
    }
    expect(terminalAt(terminals, street('high_street', 59))?.id).toBe('terminal_1');
    expect(terminalAt(terminals, street('high_street', 61.4))?.id).toBe('terminal_1');
    expect(terminalAt(terminals, street('banyan_row', 59, 18))?.id).toBe('terminal_3');
  });

  it('are out of reach two tiles along, and from nowhere', () => {
    expect(terminalAt(terminals, street('high_street', 58))).toBeUndefined();
    expect(terminalAt(terminals, street('high_street', 61.6))).toBeUndefined();
    expect(terminalAt(terminals, street('high_street', 51))).toBeUndefined();
    expect(terminalAt(terminals, undefined)).toBeUndefined();
  });

  it('are only in reach on their own map', () => {
    expect(terminalAt(terminals, street('lychee_lane', 60))).toBeUndefined();
    expect(terminalAt(terminals, { x: 60, y: 15 })).toBeUndefined();
  });
});
