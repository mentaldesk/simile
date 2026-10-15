import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { server, type Line, type Position, type SnapshotMessage } from '../net';
import { chatTarget, Dialogue } from './dialogue';
import { CHAT_RANGE_TILES, EARSHOT_TILES, LOG_LIMIT } from './tuning';
import { PLAYER_ID, type WorldView } from './world-view';

function viewOf(positions: Record<string, Position | undefined>): WorldView {
  return {
    positionOf: (id) => positions[id],
    npcIds: () => Object.keys(positions).filter((id) => id !== PLAYER_ID),
    bubbleAnchor: () => ({ x: 0, y: 0 }),
  };
}

describe('chatTarget', () => {
  it('picks the nearest NPC within range', () => {
    const view = viewOf({
      player: { x: 10, y: 10 },
      mei: { x: 12, y: 10 },
      viktor: { x: 10, y: 11.5 },
      suki: { x: 11, y: 11 },
    });
    expect(chatTarget(view)).toBe('suki');
  });

  it('includes an NPC right at the edge of the range', () => {
    expect(chatTarget(viewOf({ player: { x: 0, y: 0 }, mei: { x: CHAT_RANGE_TILES, y: 0 } }))).toBe(
      'mei',
    );
  });

  it('picks nobody when every NPC is out of range', () => {
    const view = viewOf({ player: { x: 0, y: 0 }, mei: { x: CHAT_RANGE_TILES + 0.1, y: 0 } });
    expect(chatTarget(view)).toBeUndefined();
  });

  it('skips NPCs that are nowhere, and picks nobody when the player is nowhere', () => {
    expect(
      chatTarget(viewOf({ player: { x: 0, y: 0 }, mei: undefined, suki: { x: 1, y: 1 } })),
    ).toBe('suki');
    expect(chatTarget(viewOf({ player: undefined, mei: { x: 0, y: 0 } }))).toBeUndefined();
  });
});

describe('Dialogue', () => {
  const snapshot: SnapshotMessage = {
    type: 'snapshot',
    time: '2026-03-14T08:05:00Z',
    map_id: 'village',
    entities: [
      { id: 'player', kind: 'player', name: 'Player', position: { x: 0, y: 0 } },
      { id: 'mei', kind: 'npc', name: 'Mei Lin', position: { x: 0, y: 0 } },
    ],
    conversations: [],
  };
  const view = viewOf({
    player: { x: 10, y: 10 },
    mei: { x: 12, y: 10 },
    tom: { x: 10 + EARSHOT_TILES + 1, y: 10 },
  });
  let dialogue: Dialogue;
  let stop: () => void;

  function deliver(speaker: string, text: string, duration = 2): void {
    const line: Line = {
      id: 1,
      conversation_id: 'conv_1',
      speaker,
      text,
      timestamp: '2026-03-14T08:05:00Z',
      duration,
    };
    server.dispatch(JSON.stringify({ type: 'line', line, voiced: false }));
  }

  beforeEach(() => {
    dialogue = new Dialogue(server, () => view);
    stop = dialogue.listen();
    server.dispatch(JSON.stringify(snapshot));
  });

  afterEach(() => {
    stop();
    vi.restoreAllMocks();
  });

  it('shows and logs lines within earshot, labelled by speaker', () => {
    deliver('mei', 'Morning!');

    expect(dialogue.bubbles.current()).toMatchObject([{ speaker: 'mei', text: 'Morning!' }]);
    expect(dialogue.log.entries).toEqual([
      { speaker: 'mei', name: 'Mei Lin', text: 'Morning!', to: null },
    ]);
  });

  it('ignores lines out of earshot', () => {
    deliver('tom', 'Can anyone hear me?');

    expect(dialogue.bubbles.current()).toEqual([]);
    expect(dialogue.log.entries).toEqual([]);
  });

  it("ignores the player's own lines coming back from the server", () => {
    deliver('player', 'Hi Mei');

    expect(dialogue.log.entries).toEqual([]);
  });

  it('sends what the player says to the NPC, and shows and logs it', () => {
    const send = vi.spyOn(server, 'send').mockReturnValue(true);

    expect(dialogue.say('  Hi Mei ', 'mei')).toBe(true);

    expect(send).toHaveBeenCalledWith({ type: 'player_say', text: 'Hi Mei', target: 'mei' });
    expect(dialogue.bubbles.current()).toMatchObject([{ speaker: 'player', text: 'Hi Mei' }]);
    expect(dialogue.log.entries).toEqual([
      { speaker: 'player', name: 'You', text: 'Hi Mei', to: 'Mei Lin' },
    ]);
  });

  it("doesn't send nothing", () => {
    const send = vi.spyOn(server, 'send').mockReturnValue(true);

    expect(dialogue.say('   ', 'mei')).toBe(false);
    expect(send).not.toHaveBeenCalled();
  });

  it("shows nothing when it couldn't send", () => {
    expect(dialogue.say('Hi Mei', 'mei')).toBe(false);

    expect(dialogue.bubbles.current()).toEqual([]);
    expect(dialogue.log.entries).toEqual([]);
  });

  it(`keeps the last ${LOG_LIMIT} entries`, () => {
    for (let i = 0; i <= LOG_LIMIT; i++) deliver('mei', `Line ${i}`);

    expect(dialogue.log.entries).toHaveLength(LOG_LIMIT);
    expect(dialogue.log.entries[0].text).toBe('Line 1');
  });
});
