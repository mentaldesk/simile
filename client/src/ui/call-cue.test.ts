// @vitest-environment jsdom
import { afterEach, expect, it } from 'vitest';
import { CallCue, callCue } from './call-cue';
import { HelpPanel } from './help';

afterEach(() => {
  callCue.update(undefined);
  document.body.replaceChildren();
});

function panel(): HTMLElement {
  const section = document.body.appendChild(document.createElement('section'));
  section.appendChild(document.createElement('header')).textContent = 'News';
  return section;
}

it('shows who wants to talk at the top of every panel, until they stop', () => {
  const cue = new CallCue();
  const panels = [panel(), panel()];
  panels.forEach((section) => cue.slot(section));
  const slots = () => panels.map((section) => section.firstElementChild as HTMLElement);
  expect(slots().map((slot) => slot.hidden)).toEqual([true, true]);

  cue.show('mei', 'Mei Lin');
  expect(slots().map((slot) => [slot.hidden, slot.textContent])).toEqual([
    [false, 'Mei Lin wants to talk. Esc, then Enter to reply.'],
    [false, 'Mei Lin wants to talk. Esc, then Enter to reply.'],
  ]);

  cue.update('mei');
  expect(slots()[0].hidden).toBe(false);
  cue.update(undefined);
  expect(slots().map((slot) => slot.hidden)).toEqual([true, true]);
});

it('gives a panel made while someone is calling the cue at once', () => {
  const cue = new CallCue();
  cue.show('tom', 'Tom');
  const section = panel();
  cue.slot(section);

  expect(section.querySelector<HTMLElement>('.call-cue')!.hidden).toBe(false);
});

it('shows in the controls too', () => {
  new HelpPanel(document.body).toggle();
  callCue.show('mei', 'Mei Lin');

  const shown = document.querySelector<HTMLElement>('.help .call-cue')!;
  expect(shown.hidden).toBe(false);
  expect(shown.textContent).toBe('Mei Lin wants to talk. Esc, then Enter to reply.');
});
