import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  server,
  type Conversation,
  type Line,
  type Position,
  type SnapshotMessage,
} from '../net';
import { Dialogue } from './dialogue';
import { ChatTarget } from './target';
import { CHAT_RANGE_TILES, EARSHOT_TILES, LOG_LIMIT } from './tuning';
import { PLAYER_ID, type WorldView } from './world-view';

function viewOf(positions: Record<string, Position | undefined>): WorldView {
  return {
    positionOf: (id) => positions[id],
    npcIds: () => Object.keys(positions).filter((id) => id !== PLAYER_ID),
    bubbleAnchor: () => ({ x: 0, y: 0 }),
  };
}

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
    expect(dialogue.bubbles.current()).toMatchObject([
      { speaker: 'player', text: 'Hi Mei' },
      { speaker: 'mei', text: '…', thinking: true },
    ]);
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

  function conversation(id: string, participants: Conversation['participants']): Conversation {
    return { id, participants, started: '2026-03-14T08:05:00Z', ended: null, lines: [] };
  }

  function start(id: string, ...participants: Conversation['participants']): void {
    const message = { type: 'conversation_started', conversation: conversation(id, participants) };
    server.dispatch(JSON.stringify(message));
  }

  function end(id: string): void {
    const message = { type: 'conversation_ended', conversation_id: id, ended: snapshot.time };
    server.dispatch(JSON.stringify(message));
  }

  it('knows who the player is talking with and who is busy', () => {
    start('c1', 'player', 'mei');
    start('c2', 'suki', 'tom');

    expect(dialogue.partner()).toBe('mei');
    expect(dialogue.busy('suki')).toBe(true);
    expect(dialogue.busy('mei')).toBe(false);

    end('c1');
    end('c2');
    expect(dialogue.partner()).toBeUndefined();
    expect(dialogue.busy('suki')).toBe(false);
  });

  it('keeps the chat on who the player is talking with until the server ends it', () => {
    const away = viewOf({
      player: { x: 0, y: 0 },
      mei: { x: CHAT_RANGE_TILES + 2, y: 0 },
      suki: { x: 1, y: 0 },
    });
    const target = new ChatTarget(() => away, dialogue);
    start('c1', 'player', 'mei');

    expect(target.current()).toBe('mei');
    end('c1');
    expect(target.current()).toBe('suki');
  });

  it('picks up conversations already going on from the snapshot', () => {
    const conversations = [conversation('c1', ['mei', 'player'])];
    server.dispatch(JSON.stringify({ ...snapshot, conversations }));

    expect(dialogue.partner()).toBe('mei');
  });

  it('says when an NPC starts a conversation with the player', () => {
    const invited: string[] = [];
    dialogue.onInvitation((npc) => invited.push(npc));

    start('c1', 'mei', 'player');
    start('c2', 'player', 'tom');
    start('c3', 'suki', 'tom');

    expect(invited).toEqual(['mei']);
  });

  it("logs an NPC's lines to the player as said to them", () => {
    start('conv_1', 'player', 'mei');
    deliver('mei', 'Welcome!');

    expect(dialogue.log.entries).toEqual([
      { speaker: 'mei', name: 'Mei Lin', text: 'Welcome!', to: 'You' },
    ]);
  });

  it('shows the NPC thinking until they reply', () => {
    vi.spyOn(server, 'send').mockReturnValue(true);
    start('conv_1', 'player', 'mei');
    dialogue.say('Hi Mei', 'mei');

    expect(dialogue.bubbles.current()[1]).toMatchObject({ speaker: 'mei', thinking: true });
    deliver('mei', 'Oh, hello!');
    expect(dialogue.bubbles.current()[1]).toMatchObject({ speaker: 'mei', text: 'Oh, hello!' });
  });

  it('stops the NPC thinking when the conversation ends without a reply', () => {
    vi.spyOn(server, 'send').mockReturnValue(true);
    start('conv_1', 'player', 'mei');
    dialogue.say('Hi Mei', 'mei');

    end('conv_1');

    expect(dialogue.bubbles.current().map(({ speaker }) => speaker)).toEqual(['player']);
  });

  it(`keeps the last ${LOG_LIMIT} entries`, () => {
    for (let i = 0; i <= LOG_LIMIT; i++) deliver('mei', `Line ${i}`);

    expect(dialogue.log.entries).toHaveLength(LOG_LIMIT);
    expect(dialogue.log.entries[0].text).toBe('Line 1');
  });
});
