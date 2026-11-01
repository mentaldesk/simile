// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { CONTROLS, HelpPanel, REST, VOICES } from './help';

const visible = (root: HTMLElement, selector: string) => !root.querySelector<HTMLElement>(selector)!.hidden;

describe('HelpPanel', () => {
  it('shows "? controls" until opened, then the controls until closed', () => {
    const root = document.createElement('div');
    const help = new HelpPanel(root);
    expect(visible(root, '.help-hint')).toBe(true);
    expect(root.querySelector('.help-hint')?.textContent).toBe('? controls');
    expect(help.isOpen).toBe(false);

    help.toggle();
    expect(visible(root, '.help')).toBe(true);
    expect(visible(root, '.help-hint')).toBe(false);
    help.close();
    expect(help.isOpen).toBe(false);
    expect(visible(root, '.help-hint')).toBe(true);
  });

  it('lists every key and what it does', () => {
    const root = document.createElement('div');
    new HelpPanel(root);
    const rows = [...root.querySelectorAll('.help dt')].map((dt) => [
      [...dt.querySelectorAll('kbd')].map((key) => key.textContent),
      dt.nextElementSibling?.textContent,
    ]);
    expect(rows).toEqual(CONTROLS.map(([keys, what]) => [keys, what]));
    expect(rows.map(([keys]) => (keys as string[]).join(' '))).toEqual(
      expect.arrayContaining(['← → A D', 'Shift', 'Space', '↑ W', '↓ S', 'E', 'T', 'V', 'Enter', 'Tab', 'Esc', '?']),
    );
  });

  it('gives doors to E, and stairs, ladders and the lift to the arrows', () => {
    const what = Object.fromEntries(CONTROLS.map(([keys, does]) => [keys[0], does]));
    expect(what.E).toMatch(/door/);
    expect(what['↑']).toMatch(/upstairs.*ladder.*lift up/);
    expect(what['↓']).toMatch(/downstairs.*ladder.*lift down/);
    expect(what['↑']).not.toMatch(/door/);
    expect(what.Shift).toMatch(/switch between walking and running/);
    expect(what.Space).toMatch(/jump/);
  });

  it('gives talking to T and looking at art to V, never to E', () => {
    const what = Object.fromEntries(CONTROLS.map(([keys, does]) => [keys[0], does]));
    expect(what.T).toMatch(/talk to the ringed resident.*order/);
    expect(what.V).toMatch(/look at a mural or a painting/);
    expect(what.E).not.toMatch(/talk|order|mural|painting/);
  });

  it('gives the lamp to L', () => {
    const what = Object.fromEntries(CONTROLS.map(([keys, does]) => [keys[0], does]));
    expect(what.L).toMatch(/lamp on or off.*plug to charge it/);
  });

  it('gives the character screen to C', () => {
    const what = Object.fromEntries(CONTROLS.map(([keys, does]) => [keys[0], does]));
    expect(what.C).toMatch(/character.*vitals.*body.*carry.*recipes/);
  });

  it('says voices are off unless turned on, and that greetings play either way', () => {
    const root = document.createElement('div');
    new HelpPanel(root);
    const notes = [...root.querySelectorAll('.help p')].map((note) => note.textContent);

    expect(notes).toContain(VOICES);
    expect(VOICES).toMatch(/speech bubbles unless .*SIMILE_VOICE=1 \.\/run\.sh/);
    expect(VOICES).toMatch(/Either way, each greets you out loud/);
  });

  it('says E at your bed at home rests and heals you fast', () => {
    const root = document.createElement('div');
    new HelpPanel(root);
    const notes = [...root.querySelectorAll('.help p')].map((note) => note.textContent);

    expect(notes).toContain(REST);
    expect(REST).toMatch(/Press E at your bed to rest.*maker space.*heal/);
  });
});
