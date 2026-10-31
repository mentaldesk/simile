// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { onGameKey, reply, talk as talkTo, type Talker } from './keys';

const chat = { clear: vi.fn(), cycle: vi.fn() };
const replied = vi.fn();
const talk = vi.fn();
const use = vi.fn();
const view = vi.fn();
const eat = vi.fn();
const help = { toggle: vi.fn(), close: vi.fn() };
const journal = { toggle: vi.fn(), close: vi.fn() };
const character = { toggle: vi.fn(), close: vi.fn() };
const log = { close: vi.fn() };
const pause = vi.fn();
const handler = onGameKey({ chat, reply: replied, talk, use, view, eat, help, journal, character, log, pause });

function press(target: EventTarget, key: string, init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
}

beforeEach(() => window.addEventListener('keydown', handler));

afterEach(() => {
  window.removeEventListener('keydown', handler);
  vi.clearAllMocks();
  document.body.replaceChildren();
});

describe('with nothing focused', () => {
  it('Enter talks, Esc clears the chat and closes the log, and Tab picks who the chat is to', () => {
    expect(press(document.body, 'Enter').defaultPrevented).toBe(true);
    press(document.body, 'Escape');
    expect(press(document.body, 'Tab').defaultPrevented).toBe(true);
    press(document.body, 'Tab', { shiftKey: true });

    expect(replied).toHaveBeenCalledOnce();
    expect(chat.clear).toHaveBeenCalledOnce();
    expect(log.close).toHaveBeenCalledOnce();
    expect(chat.cycle.mock.calls).toEqual([[1], [-1]]);
  });

  it('Esc asks for the pause menu before it closes anything', () => {
    press(document.body, 'Escape');

    expect(pause).toHaveBeenCalledOnce();
    expect(pause.mock.invocationCallOrder[0]).toBeLessThan(help.close.mock.invocationCallOrder[0]);
  });

  it('? shows or hides the controls, and Esc hides them', () => {
    expect(press(document.body, '?', { shiftKey: true }).defaultPrevented).toBe(true);
    press(document.body, '?', { shiftKey: true, repeat: true });
    press(document.body, 'Escape');

    expect(help.toggle).toHaveBeenCalledOnce();
    expect(help.close).toHaveBeenCalledOnce();
  });

  it('J shows or hides the journal in place of the controls, and Esc hides it', () => {
    expect(press(document.body, 'j').defaultPrevented).toBe(true);
    press(document.body, 'J', { shiftKey: true });
    press(document.body, 'j', { repeat: true });
    press(document.body, 'j', { metaKey: true });
    expect(journal.toggle).toHaveBeenCalledTimes(2);
    expect(help.close).toHaveBeenCalledTimes(2);

    press(document.body, '?', { shiftKey: true });
    press(document.body, 'Escape');
    expect(journal.close).toHaveBeenCalledTimes(2);
    expect(use).not.toHaveBeenCalled();
  });

  it('C shows or hides the character screen in place of the journal and the controls, and Esc hides it', () => {
    expect(press(document.body, 'c').defaultPrevented).toBe(true);
    press(document.body, 'C', { shiftKey: true });
    press(document.body, 'c', { repeat: true });
    press(document.body, 'c', { ctrlKey: true });
    expect(character.toggle).toHaveBeenCalledTimes(2);
    expect(journal.close).toHaveBeenCalledTimes(2);
    expect(help.close).toHaveBeenCalledTimes(2);

    press(document.body, 'j');
    press(document.body, 'Escape');
    expect(character.close).toHaveBeenCalledTimes(2);
    expect(use).not.toHaveBeenCalled();
  });

  it('E uses what is here, but not held down or with a modifier, and never talks', () => {
    press(document.body, 'e');
    press(document.body, 'E', { shiftKey: true });
    press(document.body, 'e', { repeat: true });
    press(document.body, 'e', { metaKey: true });
    press(document.body, 'e', { ctrlKey: true });

    expect(use).toHaveBeenCalledTimes(2);
    expect(replied).not.toHaveBeenCalled();
    expect(talk).not.toHaveBeenCalled();
    expect(view).not.toHaveBeenCalled();
  });

  it('T talks or orders, without typing the T into the chat box, but not held down or with a modifier', () => {
    expect(press(document.body, 't').defaultPrevented).toBe(true);
    press(document.body, 'T', { shiftKey: true });
    press(document.body, 't', { repeat: true });
    press(document.body, 't', { metaKey: true });

    expect(talk).toHaveBeenCalledTimes(2);
    expect(use).not.toHaveBeenCalled();
  });

  it('V looks at a mural or a painting, but not held down or with a modifier', () => {
    expect(press(document.body, 'v').defaultPrevented).toBe(true);
    press(document.body, 'V', { shiftKey: true });
    press(document.body, 'v', { repeat: true });
    press(document.body, 'v', { ctrlKey: true });

    expect(view).toHaveBeenCalledTimes(2);
    expect(use).not.toHaveBeenCalled();
    expect(replied).not.toHaveBeenCalled();
  });

  it('F eats, but not held down or with a modifier', () => {
    expect(press(document.body, 'f').defaultPrevented).toBe(true);
    press(document.body, 'F', { shiftKey: true });
    press(document.body, 'f', { repeat: true });
    press(document.body, 'f', { metaKey: true });

    expect(eat).toHaveBeenCalledTimes(2);
    expect(use).not.toHaveBeenCalled();
  });
});

it.each(['input', 'textarea', 'a', 'button'])('leaves keys on a focused %s alone', (tag) => {
  const element = document.body.appendChild(document.createElement(tag));

  const enter = press(element, 'Enter');
  const tab = press(element, 'Tab');
  press(element, 'Escape');
  press(element, 'e');
  press(element, 't');
  press(element, 'v');
  press(element, 'f');
  press(element, 'j');
  press(element, 'c');
  press(element, '?');

  expect(enter.defaultPrevented).toBe(false);
  expect(tab.defaultPrevented).toBe(false);
  expect(replied).not.toHaveBeenCalled();
  expect(chat.clear).not.toHaveBeenCalled();
  expect(pause).not.toHaveBeenCalled();
  expect(chat.cycle).not.toHaveBeenCalled();
  expect(use).not.toHaveBeenCalled();
  expect(talk).not.toHaveBeenCalled();
  expect(view).not.toHaveBeenCalled();
  expect(eat).not.toHaveBeenCalled();
  expect(help.toggle).not.toHaveBeenCalled();
  expect(journal.toggle).not.toHaveBeenCalled();
  expect(character.toggle).not.toHaveBeenCalled();
});

describe('T and Enter', () => {
  let reading: boolean;
  let ringed: string | undefined;
  let talker: Talker;

  beforeEach(() => {
    reading = false;
    ringed = undefined;
    talker = {
      chat: { choose: vi.fn(), open: vi.fn() },
      log: {
        get isReading() {
          return reading;
        },
        toggle: () => (reading = !reading),
        close: () => (reading = false),
      },
      ringed: () => ringed,
    };
  });

  it.each([
    ['T', () => talkTo(talker, undefined)],
    ['Enter', () => reply(talker)],
  ])('%s with nobody near opens the log to read, and closes it again', (_, press) => {
    press();
    expect(reading).toBe(true);
    ringed = 'priya';
    press();
    expect(reading).toBe(false);
    expect(talker.chat.open).not.toHaveBeenCalled();
  });

  it.each([
    ['T', () => talkTo(talker, undefined)],
    ['Enter', () => reply(talker)],
  ])('%s near a resident talks to them', (_, press) => {
    ringed = 'priya';
    press();
    expect(talker.chat.open).toHaveBeenCalledOnce();
    expect(reading).toBe(false);
  });

  it('T at a counter orders from whoever serves there, closing the log, even with nobody else near', () => {
    reading = true;
    talkTo(talker, { serving: 'odalys' });
    expect(talker.chat.choose).toHaveBeenCalledWith('odalys');
    expect(talker.chat.open).toHaveBeenCalledOnce();
    expect(reading).toBe(false);
  });

  it('T at an empty counter tries the chat, as before, rather than reading the log', () => {
    talkTo(talker, { serving: undefined });
    expect(talker.chat.choose).not.toHaveBeenCalled();
    expect(talker.chat.open).toHaveBeenCalledOnce();
    expect(reading).toBe(false);
  });
});
