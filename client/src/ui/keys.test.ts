// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { onGameKey } from './keys';

const chat = { open: vi.fn(), clear: vi.fn(), cycle: vi.fn() };
const news = vi.fn();
const help = { toggle: vi.fn(), close: vi.fn() };
const handler = onGameKey({ chat, news, help });

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

  it('E opens the news, but not held down or with a modifier', () => {
    press(document.body, 'e');
    press(document.body, 'E', { shiftKey: true });
    press(document.body, 'e', { repeat: true });
    press(document.body, 'e', { metaKey: true });
    press(document.body, 'e', { ctrlKey: true });

    expect(news).toHaveBeenCalledTimes(2);
  });
});

it.each(['input', 'textarea', 'a', 'button'])('leaves keys on a focused %s alone', (tag) => {
  const element = document.body.appendChild(document.createElement(tag));

  const enter = press(element, 'Enter');
  const tab = press(element, 'Tab');
  press(element, 'Escape');
  press(element, 'e');
  press(element, '?');

  expect(enter.defaultPrevented).toBe(false);
  expect(tab.defaultPrevented).toBe(false);
  expect(chat.open).not.toHaveBeenCalled();
  expect(chat.clear).not.toHaveBeenCalled();
  expect(chat.cycle).not.toHaveBeenCalled();
  expect(news).not.toHaveBeenCalled();
  expect(help.toggle).not.toHaveBeenCalled();
});
