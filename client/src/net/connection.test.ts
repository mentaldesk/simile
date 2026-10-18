import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { encodeAudioChunk } from './audio';
import { ServerConnection, type Socket } from './connection';
import type {
  ClientMessage,
  ClockMessage,
  EntityMovedMessage,
  MuralsMessage,
  PaintingsMessage,
  PlayerMoveMessage,
  SnapshotMessage,
  WatchNpcMessage,
  WorksMessage,
} from './protocol';

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
const clock: ClockMessage = { type: 'clock', time: '2026-03-14T09:10:03Z', speed: 1 };
const moved: EntityMovedMessage = {
  type: 'entity_moved',
  entity_id: 'mei',
  position: { x: 4.5, y: 6 },
};
const works: WorksMessage = {
  type: 'works',
  works: [
    {
      work_id: 'work_1',
      title: 'The Footbridge',
      artist: { id: 'viktor', name: 'Viktor Petrov' },
      form: 'plain verse about old bridges',
      text: 'They built it for a hundred years.\nThe arch has held for ninety-one.',
      statement: 'Things last when people look after them.',
      created: '2026-03-14T08:40:00Z',
      read: false,
    },
  ],
};
const murals: MuralsMessage = {
  type: 'murals',
  walls: [
    {
      id: 'square_north',
      x: 12,
      y: 8,
      width: 4,
      face: 'south',
      bottom: 0,
      top: 1,
      mural: {
        work_id: 'work_2',
        title: 'Who Owns the Sky',
        artist: { id: 'suki', name: 'Suki Tanaka' },
        statement: 'The sky was the one place nobody filled with forms.',
        image: '/api/works/work_2.png',
      },
    },
    { id: 'park_east', x: 30, y: 14, width: 3, face: 'east', bottom: 0.2, top: 2, mural: null },
  ],
};
const paintings: PaintingsMessage = {
  type: 'paintings',
  frames: [
    {
      id: 'painting_1',
      map: 'gallery',
      painting: {
        work_id: 'work_4',
        title: "Low Tide, Six O'Clock",
        artist: { id: 'mei', name: 'Mei Lin' },
        statement: 'The mud flats are the only time the river slows down enough to look at.',
        image: '/api/gallery/work_4.png',
      },
    },
    { id: 'painting_2', map: 'gallery', painting: null },
  ],
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

  it.each([
    ['http://localhost:5173/', 'ws://localhost:5173/ws'],
    ['https://simile.test/play?debug', 'wss://simile.test/ws'],
  ])('connects to /ws on the origin of %s by default', (page, expected) => {
    vi.stubGlobal('window', { location: new URL(page) });
    const urls: string[] = [];
    const sameOrigin = new ServerConnection(undefined, (url) => {
      urls.push(url);
      return new FakeSocket(url);
    });

    sameOrigin.connect();
    sameOrigin.close();
    vi.unstubAllGlobals();

    expect(urls).toEqual([expected]);
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

  it('passes over messages nothing handles, like the clock after the snapshot', () => {
    const received = vi.fn();
    connection.on('snapshot', received);
    connection.on('entity_moved', received);
    connection.connect();
    latest().open();

    for (const message of [snapshot, clock, moved]) latest().deliver(JSON.stringify(message));

    expect(received.mock.calls).toEqual([[snapshot], [moved]]);
  });

  it('delivers positions with their map, and without one from older servers', () => {
    const inside: SnapshotMessage = {
      ...snapshot,
      entities: [
        { id: 'mei', kind: 'npc', name: 'Mei Lin', position: { x: 4, y: 6, map: 'gallery' } },
      ],
    };
    const through: EntityMovedMessage = {
      type: 'entity_moved',
      entity_id: 'mei',
      position: { x: 31, y: 13, map: 'village' },
    };
    const received = vi.fn();
    connection.on('snapshot', received);
    connection.on('entity_moved', received);

    for (const message of [inside, through, moved]) connection.dispatch(JSON.stringify(message));

    expect(received.mock.calls).toEqual([[inside], [through], [moved]]);
  });

  it('delivers poses and facings, and entities without them from older servers', () => {
    const seated: SnapshotMessage = {
      ...snapshot,
      entities: [{ ...snapshot.entities[0], pose: 'sitting', facing: 'west' }],
    };
    const looking: EntityMovedMessage = {
      type: 'entity_moved',
      entity_id: 'mei',
      position: { x: 6, y: 3, map: 'gallery' },
      pose: 'looking',
      facing: 'north',
    };
    const received = vi.fn();
    connection.on('snapshot', received);
    connection.on('entity_moved', received);

    for (const message of [seated, looking, snapshot, moved]) connection.dispatch(JSON.stringify(message));

    expect(received.mock.calls).toEqual([[seated], [looking], [snapshot], [moved]]);
  });

  it('delivers the clock to its handlers', () => {
    const received = vi.fn();
    connection.on('clock', received);

    connection.dispatch(JSON.stringify(clock));

    expect(received).toHaveBeenCalledWith(clock);
  });

  it('delivers works, murals and paintings to their handlers', () => {
    const received = vi.fn();
    connection.on('works', received);
    connection.on('murals', received);
    connection.on('paintings', received);

    for (const message of [works, murals, paintings]) connection.dispatch(JSON.stringify(message));

    expect(received.mock.calls).toEqual([[works], [murals], [paintings]]);
  });

  it('passes over paintings when nothing handles them, as clients before the gallery do', () => {
    const received = vi.fn();
    connection.on('murals', received);

    for (const message of [paintings, murals]) connection.dispatch(JSON.stringify(message));

    expect(received.mock.calls).toEqual([[murals]]);
  });

  it('decodes binary frames as audio chunks', () => {
    const chunk = { lineId: 6, sequence: 1, last: false, samples: Int16Array.of(5, -5) };
    const received = vi.fn();
    connection.on('audio_chunk', received);
    connection.connect();

    latest().deliver(encodeAudioChunk(chunk));

    expect(received).toHaveBeenCalledWith(chunk);
  });

  it('handles frames passed to dispatch as if the server sent them', () => {
    const received = vi.fn();
    connection.on('entity_moved', received);

    connection.dispatch(JSON.stringify(moved));

    expect(received).toHaveBeenCalledWith(moved);
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

  it('sends player_move with the map the player is on, or without one for the village', () => {
    const moves: PlayerMoveMessage[] = [
      { type: 'player_move', position: { x: 10, y: 11.5, map: 'coffee_shop' } },
      { type: 'player_move', position: { x: 31, y: 13 } },
    ];
    connection.connect();
    latest().open();

    for (const move of moves) connection.send(move);

    expect(latest().sent.map((text) => JSON.parse(text))).toEqual(moves);
  });

  it('sends watch_npc with an NPC id, and with null to stop watching', () => {
    const watches: WatchNpcMessage[] = [
      { type: 'watch_npc', npc_id: 'mei' },
      { type: 'watch_npc', npc_id: null },
    ];
    connection.connect();
    latest().open();

    for (const watch of watches) connection.send(watch);

    expect(latest().sent.map((text) => JSON.parse(text))).toEqual(watches);
  });

  it('sends list_works, and read_work with a work id', () => {
    const messages: ClientMessage[] = [
      { type: 'list_works' },
      { type: 'read_work', work_id: 'work_1' },
    ];
    connection.connect();
    latest().open();

    for (const message of messages) connection.send(message);

    expect(latest().sent.map((text) => JSON.parse(text))).toEqual(messages);
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
