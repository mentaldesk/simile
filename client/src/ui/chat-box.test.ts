// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it, vi, type MockInstance } from 'vitest';
import { server, type Conversation, type Position, type SnapshotMessage } from '../net';
import { ChatBox } from './chat-box';
import { Dialogue } from './dialogue';
import { ChatTarget } from './target';
import { CHAT_RANGE_TILES } from './tuning';
import { PLAYER_ID, type WorldView } from './world-view';

const positions: Record<string, Position> = {};
const view: WorldView = {
  positionOf: (id) => positions[id],
  npcIds: () => Object.keys(positions).filter((id) => id !== PLAYER_ID),
  bubbleAnchor: () => undefined,
};

const snapshot: SnapshotMessage = {
  type: 'snapshot',
  time: '2026-03-14T08:05:00Z',
  map_id: 'village',
  entities: [
    { id: 'player', kind: 'player', name: 'Player', position: { x: 10, y: 10 } },
    { id: 'ingrid', kind: 'npc', name: 'Ingrid Salazar-Holm', position: { x: 11, y: 10 } },
    { id: 'kofi', kind: 'npc', name: 'Kofi Lindqvist-Mensah', position: { x: 9, y: 11 } },
    { id: 'marguerite', kind: 'npc', name: 'Marguerite Oyelaran', position: { x: 10, y: 12 } },
    { id: 'tobias', kind: 'npc', name: 'Tobias Fallon', position: { x: 12, y: 11 } },
  ],
  conversations: [],
};

let dialogue: Dialogue;
let stop: () => void;
let chat: ChatBox;
let send: MockInstance<typeof server.send>;

const label = () => document.querySelector('.dialogue-chat span')!.textContent;
const hint = () => document.querySelector<HTMLElement>('.dialogue-hint')!;
const input = () => document.querySelector('input')!;
const isOpen = () => !document.querySelector<HTMLElement>('.dialogue-chat')!.hidden;

function press(key: string, shiftKey = false): void {
  input().dispatchEvent(new KeyboardEvent('keydown', { key, shiftKey, bubbles: true }));
}

function type(text: string): void {
  input().value = text;
  document.querySelector('form')!.requestSubmit();
}

function conversation(id: string, participants: Conversation['participants']): Conversation {
  return { id, participants, started: snapshot.time, ended: null, lines: [] };
}

beforeEach(() => {
  for (const { id, position } of snapshot.entities) positions[id] = position;
  dialogue = new Dialogue(server, () => view);
  stop = dialogue.listen();
  server.dispatch(JSON.stringify(snapshot));
  chat = new ChatBox(document.body, dialogue, new ChatTarget(() => view, dialogue));
  dialogue.onInvitation((npcId) => chat.invite(npcId));
  send = vi.spyOn(server, 'send').mockReturnValue(true);
});

afterEach(() => {
  stop();
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

it('opens to the nearest NPC, and Tab and Shift+Tab change who it is to', () => {
  chat.open();
  expect(label()).toBe('To Ingrid Salazar-Holm:');

  press('Tab');
  expect(label()).toBe('To Kofi Lindqvist-Mensah:');
  press('Tab');
  expect(label()).toBe('To Marguerite Oyelaran:');
  press('Tab', true);
  press('Tab', true);
  press('Tab', true);
  expect(label()).toBe('To Tobias Fallon:');

  type('Hello Tobias');
  expect(send).toHaveBeenCalledWith({ type: 'player_say', text: 'Hello Tobias', target: 'tobias' });
});

it('opens to an NPC the player clicked', () => {
  chat.choose('marguerite');
  chat.open();

  expect(label()).toBe('To Marguerite Oyelaran:');
  chat.choose('kofi');
  expect(label()).toBe('To Kofi Lindqvist-Mensah:');
});

it('says why it cannot choose an NPC who is busy or too far away', () => {
  const others = conversation('c1', ['kofi', 'tobias']);
  server.dispatch(JSON.stringify({ type: 'conversation_started', conversation: others }));
  positions.marguerite = { x: 10, y: 10 + CHAT_RANGE_TILES + 1 };
  chat.open();

  chat.choose('kofi');
  expect(hint().textContent).toBe('Kofi Lindqvist-Mensah is talking with someone else.');
  chat.choose('marguerite');
  expect(hint().textContent).toBe('Marguerite Oyelaran is too far away.');
  press('Tab');
  expect(label()).toBe('To Ingrid Salazar-Holm:');
});

it('closes on Esc and forgets the choice', () => {
  chat.choose('tobias');
  chat.open();
  press('Escape');

  expect(isOpen()).toBe(false);
  chat.open();
  expect(label()).toBe('To Ingrid Salazar-Holm:');
});

it('switches from who the player is talking with to someone they chose', () => {
  const first = conversation('c1', ['player', 'marguerite']);
  server.dispatch(JSON.stringify({ type: 'conversation_started', conversation: first }));
  chat.open();
  expect(label()).toBe('To Marguerite Oyelaran:');

  chat.choose('ingrid');
  expect(label()).toBe('To Ingrid Salazar-Holm:');
  type('Sorry, one moment. Ingrid, have you got a minute?');
  expect(send).toHaveBeenLastCalledWith(expect.objectContaining({ target: 'ingrid' }));

  server.dispatch(
    JSON.stringify({ type: 'conversation_ended', conversation_id: 'c1', ended: snapshot.time }),
  );
  const second = conversation('c2', ['player', 'ingrid']);
  server.dispatch(JSON.stringify({ type: 'conversation_started', conversation: second }));
  chat.open();
  expect(label()).toBe('To Ingrid Salazar-Holm:');
});

it("doesn't send to an NPC who walked off while the player typed", () => {
  chat.open();
  positions.ingrid = { x: 10 + CHAT_RANGE_TILES + 2, y: 10 };
  expect(label()).toBe('To Ingrid Salazar-Holm:');

  type('Wait!');
  expect(send).not.toHaveBeenCalled();
  expect(hint().textContent).toBe('Ingrid Salazar-Holm is too far away.');
  expect(isOpen()).toBe(true);

  press('Tab');
  type('Kofi, where did Ingrid go?');
  expect(send).toHaveBeenCalledWith(expect.objectContaining({ target: 'kofi' }));
});

it('replies to an NPC who starts talking to the player, whoever the player chose', () => {
  chat.choose('tobias');
  const invitation = conversation('c1', ['kofi', 'player']);
  server.dispatch(JSON.stringify({ type: 'conversation_started', conversation: invitation }));

  expect(hint().textContent).toBe('Kofi Lindqvist-Mensah wants to talk. Press Enter to reply.');
  chat.open();
  expect(label()).toBe('To Kofi Lindqvist-Mensah:');
});
