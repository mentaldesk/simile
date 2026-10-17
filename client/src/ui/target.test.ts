import { describe, expect, it } from 'vitest';
import type { Position } from '../net';
import { ChatTarget, claimClicks, clicked, type Talks } from './target';
import { CHAT_RANGE_TILES } from './tuning';
import { PLAYER_ID, TILE_PX, type WorldView } from './world-view';

type Positions = Record<string, Position | undefined>;

function viewOf(positions: Positions): WorldView {
  const anchor = (id: string) => {
    const at = positions[id];
    return at && { x: at.x * TILE_PX, y: at.y * TILE_PX };
  };
  return {
    positionOf: (id) => positions[id],
    npcIds: () => Object.keys(positions).filter((id) => id !== PLAYER_ID),
    bubbleAnchor: anchor,
    spriteOf: (id) => {
      const at = anchor(id);
      const box = at && { x: at.x - TILE_PX / 2, y: at.y, width: TILE_PX, height: 1.5 * TILE_PX };
      return box && { box, depth: box.y };
    },
  };
}

const free: Talks = { partner: () => undefined, busy: () => false };

function targets(positions: Positions, talks: Talks = free): ChatTarget {
  return new ChatTarget(() => viewOf(positions), talks);
}

describe('without a choice', () => {
  it('picks the nearest NPC within range', () => {
    const chat = targets({
      player: { x: 10, y: 10 },
      mei: { x: 12, y: 10 },
      viktor: { x: 10, y: 11.5 },
      suki: { x: 11, y: 11 },
    });
    expect(chat.current()).toBe('suki');
  });

  it('includes an NPC right at the edge of the range', () => {
    const chat = targets({ player: { x: 0, y: 0 }, mei: { x: CHAT_RANGE_TILES, y: 0 } });
    expect(chat.current()).toBe('mei');
  });

  it('picks nobody when every NPC is out of range', () => {
    const chat = targets({ player: { x: 0, y: 0 }, mei: { x: CHAT_RANGE_TILES + 0.1, y: 0 } });
    expect(chat.current()).toBeUndefined();
  });

  it('picks who the player is talking with, however far away they are', () => {
    const positions = {
      player: { x: 0, y: 0 },
      mei: { x: 1, y: 0 },
      suki: { x: CHAT_RANGE_TILES + 2, y: 0 },
    };
    expect(targets(positions, { partner: () => 'suki', busy: () => false }).current()).toBe('suki');
  });

  it('skips NPCs who are talking with someone else', () => {
    const positions = { player: { x: 0, y: 0 }, mei: { x: 1, y: 0 }, suki: { x: 2, y: 0 } };

    expect(targets(positions, { ...free, busy: (id) => id === 'mei' }).current()).toBe('suki');
    expect(targets(positions, { ...free, busy: () => true }).current()).toBeUndefined();
  });

  it('skips NPCs that are nowhere, and picks nobody when the player is nowhere', () => {
    expect(targets({ player: { x: 0, y: 0 }, mei: undefined, suki: { x: 1, y: 1 } }).current()).toBe(
      'suki',
    );
    expect(targets({ player: undefined, mei: { x: 0, y: 0 } }).current()).toBeUndefined();
  });
});

describe('Tab', () => {
  const cluster = {
    player: { x: 10, y: 10 },
    mei: { x: 11, y: 10 },
    viktor: { x: 10, y: 12 },
    suki: { x: 12, y: 11 },
    kofi: { x: 9, y: 11 },
    tom: { x: 10 + CHAT_RANGE_TILES + 1, y: 10 },
  };

  it('goes through the NPCs in range from the nearest, round and back', () => {
    const chat = targets(cluster);

    expect(chat.reachable()).toEqual(['mei', 'kofi', 'viktor', 'suki']);
    expect(chat.current()).toBe('mei');
    expect([1, 1, 1, 1].map(() => chat.cycle(1))).toEqual(['kofi', 'viktor', 'suki', 'mei']);
    expect(chat.cycle(-1)).toBe('suki');
    expect(chat.current()).toBe('suki');
  });

  it.each([
    [1, 'kofi'],
    [-1, 'suki'],
  ] as const)('goes by %i from an NPC who walked out of range to %s', (step, expected) => {
    const positions: Positions = { ...cluster };
    const chat = targets(positions);

    chat.hold();
    positions.mei = { x: 20, y: 20 };
    expect(chat.cycle(step)).toBe(expected);
  });

  it('finds nobody when nobody is in range', () => {
    expect(targets({ ...cluster, player: { x: 0, y: 0 } }).cycle(1)).toBeUndefined();
  });

  it('skips NPCs talking with someone else, but not who the player is talking with', () => {
    const chat = targets(cluster, { partner: () => 'tom', busy: (id) => id === 'kofi' });

    expect(chat.reachable()).toEqual(['mei', 'viktor', 'suki', 'tom']);
    expect(chat.current()).toBe('tom');
    expect(chat.cycle(1)).toBe('mei');
  });
});

describe('choosing', () => {
  it('beats the nearest NPC and who the player is talking with', () => {
    const positions = { player: { x: 0, y: 0 }, mei: { x: 1, y: 0 }, suki: { x: 2, y: 0 } };
    const chat = targets(positions, { ...free, partner: () => 'mei' });

    chat.choose('suki');
    expect(chat.current()).toBe('suki');
  });

  it('lasts until the NPC is out of range or busy, then falls back', () => {
    const positions: Positions = { player: { x: 0, y: 0 }, mei: { x: 1, y: 0 }, suki: { x: 2, y: 0 } };
    let busy = '';
    const chat = targets(positions, { ...free, busy: (id) => id === busy });

    chat.choose('suki');
    positions.suki = { x: CHAT_RANGE_TILES + 1, y: 0 };
    expect(chat.current()).toBe('mei');
    positions.suki = { x: 2, y: 0 };
    expect(chat.current()).toBe('mei');

    chat.choose('suki');
    busy = 'suki';
    expect(chat.current()).toBe('mei');
  });

  it('keeps who the player is talking with however far they walk', () => {
    const positions: Positions = { player: { x: 0, y: 0 }, mei: { x: 1, y: 0 } };
    const chat = targets(positions, { ...free, partner: () => 'mei' });

    chat.choose('mei');
    positions.mei = { x: CHAT_RANGE_TILES + 2, y: 0 };
    expect(chat.current()).toBe('mei');
  });

  it('says why the player cannot talk to an NPC', () => {
    const chat = targets(
      { player: { x: 0, y: 0 }, mei: { x: 1, y: 0 }, suki: { x: 1, y: 1 }, tom: { x: 9, y: 9 } },
      { ...free, busy: (id) => id === 'suki' },
    );

    expect(chat.refusal('mei')).toBeUndefined();
    expect(chat.refusal('suki')).toBe('busy');
    expect(chat.refusal('tom')).toBe('far');
    expect(chat.refusal('nobody')).toBe('far');
  });

  it('is forgotten when cleared', () => {
    const positions = { player: { x: 0, y: 0 }, mei: { x: 1, y: 0 }, suki: { x: 2, y: 0 } };
    const chat = targets(positions);

    chat.choose('suki');
    chat.clear();
    expect(chat.current()).toBe('mei');
  });
});

describe('holding the target while the chat box is open', () => {
  it('keeps them wherever they go, and follows a new choice', () => {
    const positions: Positions = { player: { x: 0, y: 0 }, mei: { x: 1, y: 0 }, suki: { x: 2, y: 0 } };
    const chat = targets(positions);

    expect(chat.hold()).toBe('mei');
    positions.mei = { x: CHAT_RANGE_TILES + 1, y: 0 };
    expect(chat.current()).toBe('mei');

    chat.choose('suki');
    positions.mei = { x: 1, y: 0 };
    expect(chat.current()).toBe('suki');

    chat.release();
    expect(chat.current()).toBe('suki');
  });

  it('lets go when released', () => {
    const positions: Positions = { player: { x: 0, y: 0 }, mei: { x: 1, y: 0 }, suki: { x: 2, y: 0 } };
    const chat = targets(positions);

    chat.hold();
    positions.mei = { x: CHAT_RANGE_TILES + 1, y: 0 };
    chat.release();
    expect(chat.current()).toBe('suki');
  });
});

describe('clicking', () => {
  const view = viewOf({ player: { x: 2, y: 2 }, mei: { x: 3, y: 2 }, suki: { x: 4, y: 3 } });
  const on = (id: string) => {
    const anchor = view.bubbleAnchor(id)!;
    return { x: anchor.x, y: anchor.y + 10 };
  };

  it('picks the NPC under the pointer, and nobody on empty ground or the player', () => {
    expect(clicked(on('mei'), view)).toBe('mei');
    expect(clicked(on('suki'), view)).toBe('suki');
    expect(clicked({ x: 0, y: 0 }, view)).toBeUndefined();
    expect(clicked(on('player'), view)).toBeUndefined();
  });

  it('picks nobody while something else claims clicks', () => {
    let open = true;
    const unclaim = claimClicks(() => open);

    expect(clicked(on('mei'), view)).toBeUndefined();
    open = false;
    expect(clicked(on('mei'), view)).toBe('mei');
    open = true;
    unclaim();
    expect(clicked(on('mei'), view)).toBe('mei');
  });
});
