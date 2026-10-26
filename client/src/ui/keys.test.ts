// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { doorOnE, onGameKey } from './keys';

const chat = { open: vi.fn(), clear: vi.fn(), cycle: vi.fn() };
const use = vi.fn();
const view = vi.fn();
const eat = vi.fn();
const help = { toggle: vi.fn(), close: vi.fn() };
const journal = { toggle: vi.fn(), close: vi.fn() };
const character = { toggle: vi.fn(), close: vi.fn() };
const handler = onGameKey({ chat, use, view, eat, help, journal, character });

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
  it('Enter opens the chat box, Esc clears it and Tab picks who it is to', () => {
    expect(press(document.body, 'Enter').defaultPrevented).toBe(true);
    press(document.body, 'Escape');
    expect(press(document.body, 'Tab').defaultPrevented).toBe(true);
    press(document.body, 'Tab', { shiftKey: true });

    expect(chat.open).toHaveBeenCalledOnce();
    expect(chat.clear).toHaveBeenCalledOnce();
    expect(chat.cycle.mock.calls).toEqual([[1], [-1]]);
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
    expect(chat.open).not.toHaveBeenCalled();
    expect(view).not.toHaveBeenCalled();
  });

  it('T talks to the ringed resident, without typing the T into the chat box, but not held down or with a modifier', () => {
    expect(press(document.body, 't').defaultPrevented).toBe(true);
    press(document.body, 'T', { shiftKey: true });
    press(document.body, 't', { repeat: true });
    press(document.body, 't', { metaKey: true });

    expect(chat.open).toHaveBeenCalledTimes(2);
    expect(use).not.toHaveBeenCalled();
  });

  it('V looks at a mural or a painting, but not held down or with a modifier', () => {
    expect(press(document.body, 'v').defaultPrevented).toBe(true);
    press(document.body, 'V', { shiftKey: true });
    press(document.body, 'v', { repeat: true });
    press(document.body, 'v', { ctrlKey: true });

    expect(view).toHaveBeenCalledTimes(2);
    expect(use).not.toHaveBeenCalled();
    expect(chat.open).not.toHaveBeenCalled();
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
  expect(chat.open).not.toHaveBeenCalled();
  expect(chat.clear).not.toHaveBeenCalled();
  expect(chat.cycle).not.toHaveBeenCalled();
  expect(use).not.toHaveBeenCalled();
  expect(view).not.toHaveBeenCalled();
  expect(eat).not.toHaveBeenCalled();
  expect(help.toggle).not.toHaveBeenCalled();
  expect(journal.toggle).not.toHaveBeenCalled();
  expect(character.toggle).not.toHaveBeenCalled();
});

it('leaves E to a door on the player’s cell, and to what is in reach elsewhere', () => {
  const at = (keys: string[], action: string) => ({ keys, action, x: 0, y: 0 });
  expect(doorOnE([at(['E'], 'go out'), at(['↑'], 'upstairs')])).toBe(true);
  expect(doorOnE([at(['↑'], 'upstairs')])).toBe(false);
  expect(doorOnE([])).toBe(false);
});
