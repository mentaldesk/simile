import { beforeEach, describe, expect, it } from 'vitest';
import type { AudioChunk, Line, Position } from '../net';
import { encodeAudioChunk } from '../net/audio';
import { ServerConnection } from '../net/connection';
import {
  listen,
  REMEMBERED_LINES,
  VoicePlayer,
  type AudioOutput,
  type VoiceOutput,
} from './player';
import { overheardMix, partnerMix, UNPOSITIONED, type Mix } from './spatial';
import { JITTER_BUFFER_S } from './timeline';

class FakeVoice implements VoiceOutput {
  played: { at: number; samples: number[] }[] = [];
  mixes: Mix[] = [];
  closed = false;

  play(samples: Float32Array, at: number) {
    this.played.push({ at, samples: Array.from(samples) });
  }

  mix(mix: Mix) {
    this.mixes.push(mix);
  }

  close() {
    this.closed = true;
  }

  get starts() {
    return this.played.map(({ at }) => at);
  }

  get latestMix() {
    return this.mixes[this.mixes.length - 1];
  }
}

class FakeOutput implements AudioOutput {
  now = 0;
  voices: FakeVoice[] = [];

  createVoice() {
    const voice = new FakeVoice();
    this.voices.push(voice);
    return voice;
  }
}

const CHUNK = 2400;
const CHUNK_S = 0.1;

const chunk = (lineId: number, sequence: number, last = false, length = CHUNK): AudioChunk => ({
  lineId,
  sequence,
  last,
  samples: new Int16Array(length).fill(16384),
});

const line = (id: number, speaker: string, conversation = 'conv_1'): Line => ({
  id,
  conversation_id: conversation,
  speaker,
  text: 'Morning!',
  timestamp: '2026-03-14T08:05:00Z',
  duration: 1.2,
});

describe('VoicePlayer', () => {
  let output: FakeOutput;
  let where: Map<string, Position>;
  let player: VoicePlayer;

  beforeEach(() => {
    output = new FakeOutput();
    where = new Map([
      ['player', { x: 10, y: 10 }],
      ['mei', { x: 14, y: 10 }],
      ['tom', { x: 4, y: 12 }],
    ]);
    player = new VoicePlayer(output, {
      positionOf: (id) => where.get(id),
      listenerPosition: () => where.get('player'),
    });
  });

  it('plays a line’s chunks back to back after the jitter buffer', () => {
    player.learn(line(1, 'mei'));
    [0, 0.02, 0.09, 0.15].forEach((now, sequence) => {
      output.now = now;
      player.receive(chunk(1, sequence));
    });

    expect(output.voices).toHaveLength(1);
    expect(output.voices[0].starts).toEqual(
      [0, 1, 2, 3].map((i) => expect.closeTo(JITTER_BUFFER_S + i * CHUNK_S, 12)),
    );
    expect(player.underruns).toBe(0);
  });

  it('plays the samples as floats', () => {
    player.receive({ lineId: 1, sequence: 0, last: false, samples: Int16Array.of(16384, -32768) });

    expect(output.voices[0].played[0].samples).toEqual([0.5, -1]);
  });

  it('counts chunks that arrive too late to follow on', () => {
    player.receive(chunk(1, 0));
    output.now = 1;
    player.receive(chunk(1, 1));

    expect(output.voices[0].starts[1]).toBe(1 + JITTER_BUFFER_S);
    expect(player.underruns).toBe(1);
  });

  it('places the voice at its speaker', () => {
    player.learn(line(1, 'mei'));
    player.receive(chunk(1, 0));

    expect(output.voices[0].mixes).toEqual([overheardMix({ x: 10, y: 10 }, { x: 14, y: 10 })]);
    expect(output.voices[0].latestMix.pan).toBeGreaterThan(0);
  });

  it('follows the speaker and the listener as they move', () => {
    player.learn(line(1, 'mei'));
    player.receive(chunk(1, 0));
    const voice = output.voices[0];

    where.set('mei', { x: 6, y: 10 });
    player.update();
    expect(voice.latestMix).toEqual(overheardMix({ x: 10, y: 10 }, { x: 6, y: 10 }));
    expect(voice.latestMix.pan).toBeLessThan(0);

    where.set('player', { x: 6, y: 18 });
    player.update();
    expect(voice.latestMix).toEqual(overheardMix({ x: 6, y: 18 }, { x: 6, y: 10 }));
  });

  it('leaves the mix alone while nobody moves', () => {
    player.learn(line(1, 'mei'));
    player.receive(chunk(1, 0));

    player.update();
    player.update();

    expect(output.voices[0].mixes).toHaveLength(1);
  });

  it('plays the player’s partner at full volume, panned gently', () => {
    player.learn(line(1, 'mei'), true);
    player.learn(line(2, 'mei'));
    player.receive(chunk(1, 0));
    player.receive(chunk(2, 0));

    const [partner, overheard] = output.voices;
    expect(partner.mixes).toEqual([partnerMix({ x: 10, y: 10 }, { x: 14, y: 10 })]);
    expect(partner.latestMix.gain).toBe(1);
    expect(partner.latestMix.pan).toBeGreaterThan(0);
    expect(partner.latestMix.pan).toBeLessThan(overheard.latestMix.pan);
  });

  it('keeps the partner at full volume as they walk away', () => {
    player.learn(line(1, 'mei'), true);
    player.receive(chunk(1, 0));

    where.set('mei', { x: 10, y: 16 });
    player.update();

    expect(output.voices[0].latestMix).toEqual({ gain: 1, pan: 0 });
  });

  it('plays lines from different speakers at the same time', () => {
    player.learn(line(1, 'mei'));
    player.learn(line(2, 'tom'));
    for (const sequence of [0, 1, 2]) {
      player.receive(chunk(1, sequence));
      player.receive(chunk(2, sequence));
    }

    const [mei, tom] = output.voices;
    expect(mei.starts).toEqual(tom.starts);
    expect(mei.latestMix.pan).toBeGreaterThan(0);
    expect(tom.latestMix.pan).toBeLessThan(0);
  });

  it('plays a chunk with no line unpositioned', () => {
    player.receive(chunk(9, 0));

    expect(output.voices[0].mixes).toEqual([UNPOSITIONED]);
    expect(output.voices[0].starts).toEqual([JITTER_BUFFER_S]);
  });

  it('places a voice once its line arrives after the first chunk', () => {
    player.receive(chunk(1, 0));
    player.learn(line(1, 'tom'));

    expect(output.voices[0].mixes).toEqual([
      UNPOSITIONED,
      overheardMix({ x: 10, y: 10 }, { x: 4, y: 12 }),
    ]);
  });

  it('plays unpositioned while it doesn’t know where the speaker or the listener is', () => {
    player.learn(line(1, 'nobody'));
    player.receive(chunk(1, 0));
    where.delete('player');
    player.learn(line(2, 'mei'));
    player.receive(chunk(2, 0));

    expect(output.voices.map((voice) => voice.latestMix)).toEqual([UNPOSITIONED, UNPOSITIONED]);
  });

  it('closes a line’s voice once its last chunk has played', () => {
    player.learn(line(1, 'mei'));
    player.receive(chunk(1, 0));
    player.receive(chunk(1, 1, true));
    const voice = output.voices[0];

    output.now = JITTER_BUFFER_S + 2 * CHUNK_S - 0.001;
    player.update();
    expect(voice.closed).toBe(false);

    output.now = JITTER_BUFFER_S + 2 * CHUNK_S;
    player.update();
    expect(voice.closed).toBe(true);
  });

  it('keeps following the speaker until the last chunk has played', () => {
    player.learn(line(1, 'mei'));
    player.receive(chunk(1, 0, true));

    where.set('mei', { x: 10, y: 4 });
    player.update();

    expect(output.voices[0].latestMix).toEqual(overheardMix({ x: 10, y: 10 }, { x: 10, y: 4 }));
  });

  it('closes a voice whose last chunk is empty without playing anything more', () => {
    player.receive(chunk(1, 0));
    player.receive(chunk(1, 1, true, 0));

    output.now = JITTER_BUFFER_S + CHUNK_S;
    player.update();

    expect(output.voices[0].played).toHaveLength(1);
    expect(output.voices[0].closed).toBe(true);
  });

  it('closes a line that is only an empty last chunk', () => {
    player.receive(chunk(1, 0, true, 0));
    player.update();

    expect(output.voices[0].played).toHaveLength(0);
    expect(output.voices[0].closed).toBe(true);
  });

  it('forgets the speaker after the last chunk', () => {
    player.learn(line(1, 'mei'));
    player.receive(chunk(1, 0, true));
    output.now = 1;
    player.update();

    player.receive(chunk(1, 1));

    expect(output.voices).toHaveLength(2);
    expect(output.voices[1].mixes).toEqual([UNPOSITIONED]);
  });

  it('closes a voice whose chunks stop coming without a last one', () => {
    player.receive(chunk(1, 0));
    const voice = output.voices[0];

    output.now = 5;
    player.update();
    expect(voice.closed).toBe(false);

    output.now = 5.21;
    player.update();
    expect(voice.closed).toBe(true);
  });

  it('remembers only recent speakers', () => {
    for (let id = 0; id <= REMEMBERED_LINES; id++) player.learn(line(id, 'mei'));

    player.receive(chunk(0, 0));
    player.receive(chunk(1, 0));

    expect(output.voices.map((voice) => voice.latestMix)).toEqual([
      UNPOSITIONED,
      overheardMix({ x: 10, y: 10 }, { x: 14, y: 10 }),
    ]);
  });
});

describe('listen', () => {
  let output: FakeOutput;
  let player: VoicePlayer;
  let connection: ServerConnection;
  let playing: boolean;

  beforeEach(() => {
    output = new FakeOutput();
    player = new VoicePlayer(output, {
      positionOf: (id) => (id === 'mei' ? { x: 14, y: 10 } : undefined),
      listenerPosition: () => ({ x: 10, y: 10 }),
    });
    connection = new ServerConnection('ws://localhost/ws');
    playing = true;
    listen(connection, player, () => playing);
  });

  const meiNearby = overheardMix({ x: 10, y: 10 }, { x: 14, y: 10 });
  const audio = (lineId: number) =>
    connection.dispatch(
      encodeAudioChunk({ lineId, sequence: 0, last: false, samples: new Int16Array(4) }),
    );

  it('plays audio chunks from the server at their line’s speaker', () => {
    connection.dispatch(JSON.stringify({ type: 'line', line: line(5, 'mei'), voiced: true }));
    audio(5);

    expect(output.voices[0].mixes).toEqual([meiNearby]);
    expect(output.voices[0].played).toHaveLength(1);
  });

  it('learns speakers from the snapshot and new conversations', () => {
    const conversation = (id: string, lines: Line[]) => ({
      id,
      participants: ['mei', 'tom'],
      started: '2026-03-14T08:05:00Z',
      ended: null,
      lines,
    });
    connection.dispatch(
      JSON.stringify({
        type: 'snapshot',
        time: '2026-03-14T08:05:00Z',
        map_id: 'village',
        entities: [],
        conversations: [conversation('a', [line(1, 'mei')])],
      }),
    );
    connection.dispatch(
      JSON.stringify({
        type: 'conversation_started',
        conversation: conversation('b', [line(2, 'mei')]),
      }),
    );
    audio(1);
    audio(2);

    expect(output.voices.map((voice) => voice.latestMix)).toEqual([meiNearby, meiNearby]);
  });

  const meiAsPartner = partnerMix({ x: 10, y: 10 }, { x: 14, y: 10 });
  const conversation = (id: string, participants: [string, string], lines: Line[] = []) => ({
    id,
    participants,
    started: '2026-03-14T08:05:00Z',
    ended: null,
    lines,
  });
  const started = (id: string, participants: [string, string]) =>
    connection.dispatch(
      JSON.stringify({
        type: 'conversation_started',
        conversation: conversation(id, participants),
      }),
    );
  const said = (id: number, conversationId: string) =>
    connection.dispatch(
      JSON.stringify({ type: 'line', line: line(id, 'mei', conversationId), voiced: true }),
    );

  it('plays the player’s partner at full volume and overheard voices quieter', () => {
    started('mine', ['player', 'mei']);
    started('theirs', ['mei', 'tom']);
    said(1, 'mine');
    said(2, 'theirs');
    audio(1);
    audio(2);

    expect(output.voices.map((voice) => voice.latestMix)).toEqual([meiAsPartner, meiNearby]);
  });

  it('knows the player’s conversation from the snapshot', () => {
    connection.dispatch(
      JSON.stringify({
        type: 'snapshot',
        time: '2026-03-14T08:05:00Z',
        map_id: 'village',
        entities: [],
        conversations: [conversation('mine', ['mei', 'player'], [line(1, 'mei', 'mine')])],
      }),
    );
    said(2, 'mine');
    audio(1);
    audio(2);

    expect(output.voices.map((voice) => voice.latestMix)).toEqual([meiAsPartner, meiAsPartner]);
  });

  it('plays the partner’s last line at full volume after the conversation ends', () => {
    started('mine', ['player', 'mei']);
    said(1, 'mine');
    connection.dispatch(
      JSON.stringify({ type: 'conversation_ended', conversation_id: 'mine', ended: 'x' }),
    );
    said(2, 'mine');
    audio(1);
    audio(2);

    expect(output.voices.map((voice) => voice.latestMix)).toEqual([meiAsPartner, meiNearby]);
  });

  it('forgets the player’s conversations on a new snapshot', () => {
    started('mine', ['player', 'mei']);
    connection.dispatch(
      JSON.stringify({
        type: 'snapshot',
        time: '2026-03-14T08:05:00Z',
        map_id: 'village',
        entities: [],
        conversations: [],
      }),
    );
    said(1, 'mine');
    audio(1);

    expect(output.voices[0].latestMix).toEqual(meiNearby);
  });

  it('drops audio while it can’t play', () => {
    playing = false;
    audio(5);

    expect(output.voices).toHaveLength(0);
  });
});
