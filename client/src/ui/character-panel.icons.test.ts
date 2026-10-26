import { describe, expect, it } from 'vitest';
import { UNKNOWN_ITEM } from './character-panel';
import { iconUrl } from './icons';

describe('the Gear tab’s pictures', () => {
  it('has the fallback picture painted, for an item with none of its own', () => {
    expect(iconUrl(UNKNOWN_ITEM)).toBeTruthy();
  });
});
