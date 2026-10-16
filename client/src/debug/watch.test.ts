import { beforeEach, expect, it, vi } from 'vitest';
import { ServerConnection } from '../net/connection';
import type { ClientMessage, NpcStateMessage, SnapshotMessage } from '../net/protocol';
import { DebugWatch } from './watch';

const snapshot: SnapshotMessage = {
  type: 'snapshot',
  time: '2026-03-14T09:10:03Z',
  map_id: 'village',
  entities: [
    { id: 'kofi', kind: 'npc', name: 'Kofi Mensah', position: { x: 4, y: 6 } },
    { id: 'priya', kind: 'npc', name: 'Priya Nair', position: { x: 8, y: 6 } },
  ],
  conversations: [],
};

const npcState = (npcId: string, goal: string): NpcStateMessage => ({
  type: 'npc_state',
  npc_id: npcId,
  state: { goal },
});

let connection: ServerConnection;
let sent: ClientMessage[];
let watch: DebugWatch;

beforeEach(() => {
  connection = new ServerConnection('ws://test/ws');
  sent = [];
  vi.spyOn(connection, 'send').mockImplementation((message) => sent.push(message) > 0);
  watch = new DebugWatch(connection);
});

const watched = () => sent.map((message) => (message.type === 'watch_npc' ? message.npc_id : '?'));

it('watches the clicked NPC only while open', () => {
  watch.select('kofi');
  watch.toggle();
  watch.select('kofi');
  watch.select('priya');
  watch.toggle();

  expect(watched()).toEqual([null, 'kofi', 'priya', null]);
});

it('watches the same NPC again when reopened', () => {
  watch.toggle();
  watch.select('kofi');
  watch.toggle();
  watch.toggle();

  expect(watched()).toEqual([null, 'kofi', null, 'kofi']);
  expect(watch.watching).toBe('kofi');
});

it('sends the current watch again after every snapshot, null included', () => {
  connection.dispatch(JSON.stringify(snapshot));
  watch.toggle();
  watch.select('priya');
  connection.dispatch(JSON.stringify(snapshot));

  expect(watched()).toEqual([null, null, 'priya', 'priya']);
  expect(watch.names.get('priya')).toBe('Priya Nair');
});

it('keeps the latest state of the watched NPC and ignores the rest', () => {
  const changes = vi.fn();
  watch.onChange = changes;
  watch.toggle();
  watch.select('kofi');
  changes.mockClear();

  connection.dispatch(JSON.stringify(npcState('priya', 'park')));
  connection.dispatch(JSON.stringify(npcState('kofi', 'coffee_shop')));

  expect(watch.state).toEqual({ goal: 'coffee_shop' });
  expect(changes).toHaveBeenCalledOnce();

  watch.select('priya');
  expect(watch.state).toBeUndefined();
  watch.toggle();
  connection.dispatch(JSON.stringify(npcState('priya', 'park')));
  expect(watch.state).toBeUndefined();
});
