// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { server, type JournalEntry } from '../net';
import type { Clue } from '../world/clues';
import { HelpPanel } from './help';
import { EMPTY, JournalPanel, cluePrompt, journal, lookAtClue, openLeads } from './journal-panel';

const entry = (fact_id: string, name: string, learned: string, extra: Partial<JournalEntry> = {}): JournalEntry => ({
  fact_id,
  text: `What ${name} said about ${fact_id}.`,
  source: { kind: 'resident', id: name.toLowerCase(), name },
  learned,
  flushed: null,
  leads: [],
  ...extra,
});

const NOTES = entry('notes', "Aris's notes", '2026-01-02T10:05:00Z', {
  source: { kind: 'clue', id: 'aris_notes', name: "Aris's notes" },
  leads: [
    { fact_id: 'grudge_raymond', text: 'Who is R.? Ask Kofi.' },
    { fact_id: 'shouting', text: 'Tobias was up late. Ask him.' },
  ],
});
const TOBIAS = entry('shouting', 'Tobias', '2026-01-02T11:30:00Z', {
  leads: [{ fact_id: 'grudge_raymond', text: 'Who is R.? Ask Kofi.' }],
});
const RAYMOND = entry('there_raymond', 'Raymond', '2026-01-03T14:00:00Z', {
  text: '“I was at home all night.”',
  flushed: true,
});
const KOFI = entry('seen', 'Kofi', '2026-01-03T15:00:00Z', { flushed: false });

const clues: Clue[] = [
  { id: 'aris_notes', label: "Aris's notes", map: 'maker_space_floor_0', x: 3, y: 2 },
  { id: 'door_frame', label: 'The splintered door frame', map: 'maker_space_floor_0', x: 13, y: 2 },
];

const send = (entries: JournalEntry[]) => server.dispatch(JSON.stringify({ type: 'journal', entries }));
const texts = (root: HTMLElement, selector: string) =>
  [...root.querySelectorAll(selector)].map((element) => element.textContent);

afterEach(() => {
  send([]);
  document.body.replaceChildren();
});

describe('JournalPanel', () => {
  it('shows "J journal" until opened, then the journal until closed', () => {
    const root = document.body.appendChild(document.createElement('div'));
    const panel = new JournalPanel(root);
    const hint = root.querySelector<HTMLElement>('.journal-hint')!;
    expect(hint.textContent).toBe('J journal');
    expect(panel.isOpen).toBe(false);

    panel.toggle();
    expect(panel.isOpen).toBe(true);
    expect(hint.hidden).toBe(true);
    expect(texts(root, '.journal-empty')).toEqual([EMPTY]);
    panel.close();
    expect(hint.hidden).toBe(false);
    panel.stop();
  });

  it('lists the open leads, then what was learned, newest first, with who said it, when and any flush', () => {
    const root = document.body.appendChild(document.createElement('div'));
    const panel = new JournalPanel(root);
    send([NOTES, TOBIAS, RAYMOND, KOFI]);
    panel.open();

    expect(texts(root, '.journal-leads li')).toEqual(['Who is R.? Ask Kofi.', 'Tobias was up late. Ask him.']);
    expect(texts(root, '.journal-entries p')).toEqual([KOFI.text, RAYMOND.text, TOBIAS.text, NOTES.text]);
    expect(texts(root, '.journal-entries small')).toEqual([
      'Kofi · 3 Jan, 15:00',
      'Raymond · 3 Jan, 14:00flushed',
      'Tobias · 2 Jan, 11:30',
      "Aris's notes · 2 Jan, 10:05",
    ]);
    expect(texts(root, '.journal-flushed p')).toEqual([RAYMOND.text]);
    expect(root.querySelector<HTMLElement>('.journal-empty')!.hidden).toBe(true);
    panel.stop();
  });

  it('hides the leads once none are open', () => {
    const root = document.body.appendChild(document.createElement('div'));
    const panel = new JournalPanel(root);
    send([RAYMOND]);

    expect(root.querySelector<HTMLElement>('.journal-leads')!.hidden).toBe(true);
    panel.stop();
  });

  it('counts what was learned since it was last open, or since the journal first came', () => {
    send([NOTES]);
    const root = document.body.appendChild(document.createElement('div'));
    const panel = new JournalPanel(root);
    const hint = root.querySelector<HTMLElement>('.journal-hint')!;
    expect(hint.textContent).toBe('J journal');

    send([NOTES, TOBIAS, RAYMOND]);
    expect(hint.textContent).toBe('J journal · 2 new');
    expect(hint.classList.contains('journal-hint-new')).toBe(true);
    panel.open();
    send([NOTES, TOBIAS, RAYMOND, KOFI]);
    panel.close();
    expect(hint.textContent).toBe('J journal');
    panel.stop();
  });

  it('counts nothing as new in the first journal after it was made', () => {
    journal.latest = undefined;
    const root = document.body.appendChild(document.createElement('div'));
    const panel = new JournalPanel(root);
    const hint = root.querySelector<HTMLElement>('.journal-hint')!;

    send([NOTES, TOBIAS]);
    expect(hint.textContent).toBe('J journal');
    send([NOTES, TOBIAS, KOFI]);
    expect(hint.textContent).toBe('J journal · 1 new');
    panel.stop();
  });

  it('says what E does at a clue, except while a panel is open', () => {
    const root = document.body.appendChild(document.createElement('div'));
    const panel = new JournalPanel(root);
    const hint = root.querySelector<HTMLElement>('.news-hint')!;

    panel.update(clues[0]);
    expect(hint.hidden).toBe(false);
    expect(hint.textContent).toBe("Press E to look at Aris's notes.");
    panel.update(clues[0], false);
    expect(hint.hidden).toBe(true);
    panel.update(undefined);
    expect(hint.hidden).toBe(true);
    panel.open();
    panel.update(clues[0]);
    expect(hint.hidden).toBe(true);
    panel.stop();
  });
});

it('keeps the last journal for a panel made after it arrives', () => {
  send([NOTES]);
  expect(journal.latest?.entries).toEqual([NOTES]);
});

it('words a clue with its label', () => {
  expect(clues.map(cluePrompt)).toEqual([
    "Press E to look at Aris's notes.",
    'Press E to look at the splintered door frame.',
  ]);
});

it('lists each open lead once', () => {
  expect(openLeads([NOTES, TOBIAS]).map(({ fact_id }) => fact_id)).toEqual(['grudge_raymond', 'shouting']);
});

it('E at a clue picks it up and opens the journal in place of the controls', () => {
  const root = document.body.appendChild(document.createElement('div'));
  const panel = new JournalPanel(root);
  const help = new HelpPanel(root);
  const send = vi.fn();
  help.toggle();

  lookAtClue(send, panel, help);

  expect(send.mock.calls).toEqual([[{ type: 'pick_up' }]]);
  expect([panel.isOpen, help.isOpen]).toEqual([true, false]);
  panel.stop();
});
