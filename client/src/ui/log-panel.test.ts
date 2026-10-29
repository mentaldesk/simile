// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { server, type Conversation, type SnapshotMessage } from '../net';
import { ChatBox } from './chat-box';
import { Dialogue } from './dialogue';
import { LogPanel } from './log-panel';
import { ChatTarget } from './target';
import { PLAYER_ID, type WorldView } from './world-view';

const snapshot: SnapshotMessage = {
  type: 'snapshot',
  time: '2026-03-14T08:05:00Z',
  map_id: 'village',
  entities: [
    { id: PLAYER_ID, kind: 'player', name: 'Player', position: { x: 10, y: 10 } },
    { id: 'priya', kind: 'npc', name: 'Priya', position: { x: 11, y: 10 } },
    { id: 'henrietta', kind: 'npc', name: 'Henrietta', position: { x: 12, y: 10 } },
  ],
  conversations: [],
};

const view: WorldView = {
  positionOf: (id) => snapshot.entities.find((entity) => entity.id === id)?.position,
  npcIds: () => ['priya', 'henrietta'],
  bubbleAnchor: () => undefined,
  spriteOf: () => undefined,
};

let dialogue: Dialogue;
let stop: () => void;
let chat: ChatBox;
let log: LogPanel;

const shown = () => {
  log.update(chat, dialogue);
  return !document.querySelector<HTMLElement>('.dialogue-log')!.hidden;
};

function started(participants: Conversation['participants']): void {
  const conversation = { id: 'c1', participants, started: snapshot.time, ended: null, lines: [] };
  server.dispatch(JSON.stringify({ type: 'conversation_started', conversation }));
}

function ended(): void {
  server.dispatch(JSON.stringify({ type: 'conversation_ended', conversation_id: 'c1', ended: snapshot.time }));
}

function overheard(text: string): void {
  const line = { id: 1, conversation_id: 'c1', speaker: 'priya', text, timestamp: snapshot.time, duration: 2 };
  server.dispatch(JSON.stringify({ type: 'line', line, voiced: false }));
}

beforeEach(() => {
  dialogue = new Dialogue(server, () => view);
  stop = dialogue.listen();
  server.dispatch(JSON.stringify(snapshot));
  log = new LogPanel(document.body, dialogue.log);
  chat = new ChatBox(document.body, dialogue, new ChatTarget(() => view, dialogue));
  vi.spyOn(server, 'send').mockReturnValue(true);
});

afterEach(() => {
  log.stop();
  stop();
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

it('is hidden while the player only overhears others talking', () => {
  started(['priya', 'henrietta']);
  overheard("That's the pump. Someone's fixed it again.");

  expect(document.querySelector('.dialogue-log li')?.textContent).toContain('the pump');
  expect(shown()).toBe(false);
});

it('shows while the player types to someone, and hides when they stop', () => {
  chat.open();
  expect(shown()).toBe(true);

  chat.clear();
  expect(shown()).toBe(false);
});

it('shows when a resident starts talking to the player, until the conversation ends', () => {
  started(['priya', PLAYER_ID]);
  expect(shown()).toBe(true);

  ended();
  expect(shown()).toBe(false);
});
