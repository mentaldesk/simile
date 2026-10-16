import { expect, it } from 'vitest';
import { html } from './html';
import { renderPanel } from './panel';
import type { NpcState } from './state';

const names = new Map([
  ['kofi', 'Kofi Mensah'],
  ['priya', 'Priya Nair'],
  ['player', 'Player'],
]);

const state: NpcState = {
  name: 'Kofi Mensah',
  occupation: 'Street Mural Artist',
  time: '2026-03-14T09:42:10+00:00',
  goal: 'talk priya',
  walking: false,
  paused: true,
  since: '2026-03-14T09:40:00+00:00',
  until: null,
  needs: { social: 0.25, curiosity: 0.5, rest: 1 },
  options: { 'park park': 0.4, 'coffee_shop coffee_shop': 1.2, idle: -0.3 },
  values: { creativity: 0.94, adventure: 0.9 },
  relationships: [
    {
      about: 'priya',
      like: 0.81,
      trust: 0.7,
      respect: 0.66,
      familiarity: 0.4,
      flags: [
        { kind: 'grudge', description: 'took the last <b>bun</b>', open: true },
        { kind: 'debt', description: 'lent a brush', open: false },
      ],
    },
    { about: 'player', like: 0.5, trust: 0.5, respect: 0.5, familiarity: 0, flags: [] },
  ],
  memories: [
    {
      kind: 'conversation',
      content: 'Priya liked my mural.',
      timestamp: '2026-03-14T08:05:00+00:00',
      salience: 0.6,
      valence: 0.4,
    },
    {
      kind: 'news',
      content: 'The bridge is closing.',
      timestamp: '2026-03-13T18:00:00+00:00',
      salience: 0.3,
      valence: -0.2,
    },
  ],
  conversation: {
    id: 'conv',
    talking_to: 'priya',
    engagement: 0.72,
    leaving: true,
    lines: [
      { speaker: 'kofi', text: 'Morning!', timestamp: '2026-03-14T09:40:01+00:00' },
      { speaker: 'priya', text: 'Hi Kofi.', timestamp: '2026-03-14T09:40:03+00:00' },
    ],
  },
};

const text = (markup: string) =>
  markup
    .replace(/<[^>]+>/g, ' ')
    .replace(/&#(\d+);/g, (_, code) => String.fromCharCode(Number(code)))
    .replace(/\s+/g, ' ')
    .trim();

it('asks for a click until an NPC is chosen, then waits for their state', () => {
  expect(text(renderPanel({ names }))).toMatch(/^Click an NPC/);
  expect(text(renderPanel({ npcId: 'priya', names }))).toMatch(/^Priya Nair Waiting/);
});

it('shows every section of the state', () => {
  const panel = text(renderPanel({ npcId: 'kofi', state, names }));

  expect(panel).toContain('Kofi Mensah Street Mural Artist 09:42:10');
  expect(panel).toContain('Goal talk priya paused · since 09:40');
  expect(panel).toContain('Needs social 0.25 curiosity 0.50 rest 1.00');
  expect(panel).toContain('Top values creativity 0.94 adventure 0.90');
  expect(panel).toContain('Last decision coffee_shop coffee_shop 1.20 park park 0.40 idle -0.30');
  expect(panel).toContain('Priya Nair 0.81 0.70 0.66 0.40 grudge: took the last <b>bun</b>');
  expect(panel).toContain('debt: lent a brush Player 0.50 0.50 0.50 0.00');
  expect(panel).toContain('08:05 conversation Priya liked my mural. salience 0.60 · feeling +0.40');
  expect(panel).toContain('03-13 18:00 news The bridge is closing.');
  expect(panel).toContain('With Priya · engagement 0.72 · saying goodbye');
  expect(panel).toContain('Kofi Morning! Priya Hi Kofi.');
});

it('draws needs as bars and marks resolved flags', () => {
  const panel = renderPanel({ npcId: 'kofi', state, names });

  expect(panel).toContain('style="width: 25%"');
  expect(panel).toContain('<span class="resolved">debt: lent a brush</span>');
});

it('copes with a quiet NPC and a partial state', () => {
  const quiet = { ...state, relationships: [], memories: [], conversation: null };
  expect(text(renderPanel({ npcId: 'kofi', state: quiet, names }))).toContain(
    'Relationships Nobody yet. Memories Nothing yet. Conversation Not talking.',
  );

  expect(text(renderPanel({ npcId: 'kofi', state: { goal: 'idle' }, names }))).toBe(
    'Kofi Mensah Goal idle ` closes · click another NPC to switch',
  );
});

it('escapes everything it interpolates', () => {
  const markup = html`<p title="${'"x"'}">${'<script>&'}${html`<i>ok</i>`}${[1, false, null]}</p>`;

  expect(markup.text).toBe('<p title="&#34;x&#34;">&#60;script&#62;&#38;<i>ok</i>1</p>');
});
