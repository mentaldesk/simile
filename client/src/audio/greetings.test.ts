// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { server, type Conversation, type Position, type SnapshotMessage } from '../net';
import { callCue } from '../ui/call-cue';
import { Dialogue } from '../ui/dialogue';
import { NewsPanel } from '../ui/news-panel';
import { PLAYER_ID, type WorldView } from '../ui/world-view';
import { fetchGreetings, Greeter, GREETING_COOLDOWN_S, type GreetingOutput } from './greetings';
import type { PositionProvider } from './positions';
import type { Mix } from './spatial';

const GREETINGS: Record<string, string[]> = {
  mei: ['/api/greetings/mei/mei_1.m4a', '/api/greetings/mei/mei_2.m4a', '/api/greetings/mei/mei_3.m4a'],
  tom: ['/api/greetings/tom/tom_1.m4a'],
};

const snapshot: SnapshotMessage = {
  type: 'snapshot',
  time: '2026-10-22T08:05:00Z',
  map_id: 'village',
  entities: [
    { id: 'player', kind: 'player', name: 'Player', position: { x: 10, y: 10 } },
    { id: 'mei', kind: 'npc', name: 'Mei Lin', position: { x: 12, y: 10 } },
    { id: 'tom', kind: 'npc', name: 'Tom', position: { x: 8, y: 10 } },
    { id: 'suki', kind: 'npc', name: 'Suki', position: { x: 11, y: 10 } },
  ],
  conversations: [],
};

const where: Record<string, Position> = {
  player: { x: 10, y: 10 },
  mei: { x: 12, y: 10 },
  tom: { x: 8, y: 10 },
  suki: { x: 11, y: 10 },
};

const view: WorldView = {
  positionOf: (id) => where[id],
  npcIds: () => Object.keys(where).filter((id) => id !== PLAYER_ID),
  bubbleAnchor: () => ({ x: 0, y: 0 }),
  spriteOf: () => undefined,
};

const positions: PositionProvider = {
  positionOf: (id) => where[id],
  listenerPosition: () => where[PLAYER_ID],
};

class FakeOutput implements GreetingOutput {
  readonly played: { url: string; mix: Mix }[] = [];
  play(url: string, mix: Mix): void {
    this.played.push({ url, mix });
  }
}

let clock: number;
let audible: boolean;
let output: FakeOutput;
let greeter: Greeter;
let dialogue: Dialogue;
let panel: NewsPanel;
let ids = 0;
const stops: (() => void)[] = [];

function start(...participants: Conversation['participants']): void {
  const conversation = {
    id: `conv_${++ids}`,
    participants,
    started: snapshot.time,
    ended: null,
    lines: [],
  };
  server.dispatch(JSON.stringify({ type: 'conversation_started', conversation }));
}

function end(): void {
  server.dispatch(
    JSON.stringify({ type: 'conversation_ended', conversation_id: `conv_${ids}`, ended: snapshot.time }),
  );
}

function say(speaker: string): void {
  const line = {
    id: ids * 10,
    conversation_id: `conv_${ids}`,
    speaker,
    text: 'So, about the bins.',
    timestamp: snapshot.time,
    duration: 1,
  };
  server.dispatch(JSON.stringify({ type: 'line', line, voiced: false }));
}

const settled = () => new Promise((resolve) => setTimeout(resolve));
const played = () => output.played.map(({ url }) => url.split('/').pop());
const cue = () => document.querySelector<HTMLElement>('.news .call-cue')!;

beforeEach(() => {
  clock = 1000;
  audible = true;
  output = new FakeOutput();
  greeter = new Greeter(output, positions, async (id) => GREETINGS[id] ?? [], {
    now: () => clock,
    random: () => 0.5,
    canPlay: () => audible,
  });
  dialogue = new Dialogue(server, () => view);
  stops.push(dialogue.listen());
  stops.push(
    dialogue.onInvitation((npcId) => {
      void greeter.greet(npcId);
      callCue.show(npcId, dialogue.nameOf(npcId));
    }),
  );
  vi.spyOn(server, 'send').mockReturnValue(true);
  panel = new NewsPanel(document.body, server);
  stops.push(panel.stop);
  server.dispatch(JSON.stringify(snapshot));
});

afterEach(() => {
  stops.splice(0).forEach((stop) => stop());
  callCue.update(undefined);
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe('greetings', () => {
  it('plays one when a resident starts talking to the player, panned towards them', async () => {
    start('mei', 'player');
    await settled();

    expect(played()).toEqual(['mei_2.m4a']);
    const [{ mix }] = output.played;
    expect(mix.gain).toBe(1);
    expect(mix.pan).toBeGreaterThan(0);
  });

  it('plays while the news panel is open, which shows who wants to talk', async () => {
    panel.open('News terminal on the square');
    expect(cue().hidden).toBe(true);

    start('mei', 'player');
    await settled();

    expect(panel.isOpen).toBe(true);
    expect(played()).toEqual(['mei_2.m4a']);
    expect(cue().hidden).toBe(false);
    expect(cue().textContent).toBe('Mei Lin wants to talk. Esc, then Enter to reply.');

    end();
    callCue.update(dialogue.partner());
    expect(cue().hidden).toBe(true);
  });

  it("doesn't play again for the same resident within the cooldown", async () => {
    start('mei', 'player');
    say('mei');
    say('mei');
    end();
    clock += GREETING_COOLDOWN_S - 1;
    start('mei', 'player');
    start('tom', 'player');
    await settled();

    expect(played()).toEqual(['mei_2.m4a', 'tom_1.m4a']);

    clock += 1;
    start('mei', 'player');
    await settled();

    expect(played()).toEqual(['mei_2.m4a', 'tom_1.m4a', 'mei_2.m4a']);
  });

  it('picks one of their greetings at random', async () => {
    const picks = [0, 0.4, 0.99];
    greeter = new Greeter(output, positions, async (id) => GREETINGS[id] ?? [], {
      now: () => (clock += GREETING_COOLDOWN_S),
      random: () => picks.shift()!,
    });
    for (let i = 0; i < 3; i++) await greeter.greet('mei');

    expect(played()).toEqual(['mei_1.m4a', 'mei_2.m4a', 'mei_3.m4a']);
  });

  it("doesn't play when the player starts the conversation, or for residents talking to each other", async () => {
    start('player', 'mei');
    say('mei');
    start('suki', 'tom');
    await settled();

    expect(played()).toEqual([]);
  });

  it('plays nothing for a resident without greetings', async () => {
    start('suki', 'player');
    await settled();

    expect(played()).toEqual([]);
    expect(cue().textContent).toBe('Suki wants to talk. Esc, then Enter to reply.');
  });

  it("plays nothing before the page can play sound, and doesn't count that as a greeting", async () => {
    audible = false;
    start('mei', 'player');
    await settled();
    expect(played()).toEqual([]);

    audible = true;
    start('mei', 'player');
    await settled();
    expect(played()).toEqual(['mei_2.m4a']);
  });

  it('plays centred while it knows nobody’s position', async () => {
    greeter = new Greeter(output, { positionOf: () => undefined, listenerPosition: () => undefined }, async () => GREETINGS.mei);

    await greeter.greet('mei');

    expect(output.played[0].mix).toEqual({ gain: 1, pan: 0 });
  });

  it('asks the server once per resident, and again after a failure', async () => {
    const list = vi.fn<(id: string) => Promise<readonly string[]>>()
      .mockRejectedValueOnce(new Error('offline'))
      .mockResolvedValue(GREETINGS.mei);
    greeter = new Greeter(output, positions, list, { now: () => (clock += GREETING_COOLDOWN_S) });

    expect(await greeter.greet('mei')).toBe(false);
    expect(await greeter.greet('mei')).toBe(true);
    expect(await greeter.greet('mei')).toBe(true);

    expect(list).toHaveBeenCalledTimes(2);
  });
});

it("lists a resident's greetings from the server", async () => {
  const fetch = vi.fn(async () => Response.json({ greetings: GREETINGS.tom }));
  vi.stubGlobal('fetch', fetch);

  expect(await fetchGreetings('tom')).toEqual(GREETINGS.tom);
  expect(fetch).toHaveBeenCalledWith('/api/greetings/tom');

  fetch.mockResolvedValueOnce(new Response(null, { status: 500 }));
  await expect(fetchGreetings('tom')).rejects.toThrow();
  vi.unstubAllGlobals();
});
