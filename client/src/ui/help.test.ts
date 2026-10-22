// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { CONTROLS, HelpPanel, VOICES } from './help';

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
      expect.arrayContaining(['← → A D', 'Shift', '↑ W', '↓ S', 'E', 'Enter', 'Tab', 'Esc', '?']),
    );
  });

  it('gives doors to E, and stairs, ladders and the lift to the arrows', () => {
    const what = Object.fromEntries(CONTROLS.map(([keys, does]) => [keys[0], does]));
    expect(what.E).toMatch(/door.*talk to the ringed resident/);
    expect(what['↑']).toMatch(/upstairs.*ladder.*lift up/);
    expect(what['↓']).toMatch(/downstairs.*ladder.*lift down/);
    expect(what['↑']).not.toMatch(/door/);
    expect(what.Shift).toMatch(/run/);
  });

  it('says voices are off unless turned on, and that greetings play either way', () => {
    const root = document.createElement('div');
    new HelpPanel(root);
    const notes = [...root.querySelectorAll('.help p')].map((note) => note.textContent);

    expect(notes).toContain(VOICES);
    expect(VOICES).toMatch(/speech bubbles unless .*SIMILE_VOICE=1 \.\/run\.sh/);
    expect(VOICES).toMatch(/Either way, each greets you out loud/);
  });
});
