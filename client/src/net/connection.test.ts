import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { encodeAudioChunk } from './audio';
import { ServerConnection, type Socket } from './connection';
import type { EntityMovedMessage, SnapshotMessage } from './protocol';

class FakeSocket implements Socket {
  binaryType: BinaryType = 'blob';
  readyState: Socket['readyState'] = 0;
  onopen: Socket['onopen'] = null;
  onmessage: Socket['onmessage'] = null;
  onclose: Socket['onclose'] = null;
  sent: string[] = [];
  readonly url: string;

  constructor(url: string) {
    this.url = url;
  }

  send(data: string) {
    this.sent.push(data);
  }

  close() {
    this.serverCloses();
  }

  open() {
    this.readyState = 1;
    this.onopen?.call(this as unknown as WebSocket, new Event('open'));
  }

  deliver(data: string | ArrayBuffer) {
    this.onmessage?.call(this as unknown as WebSocket, new MessageEvent('message', { data }));
  }

  serverCloses() {
    this.readyState = 3;
    this.onclose?.call(this as unknown as WebSocket, new CloseEvent('close'));
  }
}

const snapshot: SnapshotMessage = {
  type: 'snapshot',
  time: '2026-03-14T09:10:03Z',
  map_id: 'village',
  entities: [{ id: 'mei', kind: 'npc', name: 'Mei Lin', position: { x: 4, y: 6 } }],
  conversations: [],
};
const moved: EntityMovedMessage = {
  type: 'entity_moved',
  entity_id: 'mei',
  position: { x: 4.5, y: 6 },
};

describe('ServerConnection', () => {
  let sockets: FakeSocket[];
  let connection: ServerConnection;
  const latest = () => sockets[sockets.length - 1];

  beforeEach(() => {
    vi.useFakeTimers();
    sockets = [];
    connection = new ServerConnection('ws://localhost/ws', (url) => {
      const socket = new FakeSocket(url);
      sockets.push(socket);
      return socket;
    });
  });

  afterEach(() => {
    connection.close();
    vi.useRealTimers();
  });

  it('connects to its URL and asks for binary frames as ArrayBuffers', () => {
    connection.connect();

    expect(latest().url).toBe('ws://localhost/ws');
    expect(latest().binaryType).toBe('arraybuffer');
  });

  it('delivers each message to the handlers for its type', () => {
    const snapshots: SnapshotMessage[] = [];
    const moves: EntityMovedMessage[] = [];
    connection.on('snapshot', (message) => snapshots.push(message));
    connection.on('entity_moved', (message) => moves.push(message));
    connection.connect();
    latest().open();

    latest().deliver(JSON.stringify(snapshot));
    latest().deliver(JSON.stringify(moved));

    expect(snapshots).toEqual([snapshot]);
    expect(moves).toEqual([moved]);
  });

  it('decodes binary frames as audio chunks', () => {
    const chunk = { lineId: 6, sequence: 1, last: false, samples: Int16Array.of(5, -5) };
    const received = vi.fn();
    connection.on('audio_chunk', received);
    connection.connect();

    latest().deliver(encodeAudioChunk(chunk));

    expect(received).toHaveBeenCalledWith(chunk);
  });

  it('stops delivering after unsubscribe', () => {
    const received = vi.fn();
    const unsubscribe = connection.on('entity_moved', received);
    connection.connect();

    unsubscribe();
    latest().deliver(JSON.stringify(moved));

    expect(received).not.toHaveBeenCalled();
  });

  it('keeps delivering when a handler throws', () => {
    const error = vi.spyOn(console, 'error').mockImplementation(() => {});
    const received = vi.fn();
    connection.on('entity_moved', () => {
      throw new Error('boom');
    });
    connection.on('entity_moved', received);
    connection.connect();

    latest().deliver(JSON.stringify(moved));

    expect(received).toHaveBeenCalledOnce();
    expect(error).toHaveBeenCalledOnce();
    error.mockRestore();
  });

  it('sends client messages as JSON once open', () => {
    connection.connect();
    const move = { type: 'player_move', position: { x: 1, y: 2 } } as const;

    expect(connection.send(move)).toBe(false);
    latest().open();
    expect(connection.send(move)).toBe(true);

    expect(latest().sent.map((text) => JSON.parse(text))).toEqual([move]);
  });

  it('reconnects with backoff until a connection opens', () => {
    connection.connect();
    latest().serverCloses();
    vi.advanceTimersByTime(249);
    expect(sockets).toHaveLength(1);

    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(2);
    latest().serverCloses();
    vi.advanceTimersByTime(499);
    expect(sockets).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(sockets).toHaveLength(3);

    latest().open();
    latest().serverCloses();
    vi.advanceTimersByTime(250);
    expect(sockets).toHaveLength(4);
  });

  it('stays closed after close()', () => {
    connection.connect();
    latest().open();

    connection.close();
    vi.advanceTimersByTime(10_000);

    expect(sockets).toHaveLength(1);
  });
});
