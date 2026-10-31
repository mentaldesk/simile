// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { CONTROLS } from './help';
import { onGameKey } from './keys';
import { PauseGate, PauseMenu } from './pause-menu';
import { PAUSE_GRACE_MS } from './tuning';

function press(target: Element, key: string, init: KeyboardEventInit = {}): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true, ...init });
  target.dispatchEvent(event);
  return event;
}

const button = (text: string) =>
  [...document.querySelectorAll<HTMLButtonElement>('.pause button')].find(
    (b) => b.textContent === text,
  )!;

function opened() {
  const exit = vi.fn();
  const menu = new PauseMenu(document.body, exit);
  menu.open();
  return { menu, exit };
}

afterEach(() => document.body.replaceChildren());

describe('PauseMenu', () => {
  it('opens on Resume, and Resume or Esc closes it', () => {
    const { menu } = opened();
    expect(menu.isOpen).toBe(true);
    expect(document.activeElement).toBe(button('Resume'));

    button('Resume').click();
    expect(menu.isOpen).toBe(false);

    menu.open();
    press(document.activeElement!, 'Escape');
    expect(menu.isOpen).toBe(false);
  });

  it('exits to the menu', () => {
    const { menu, exit } = opened();

    button('Exit to menu').click();

    expect(exit).toHaveBeenCalledOnce();
    expect(menu.isOpen).toBe(true);
  });

  it('shows the controls', () => {
    opened();
    const controls = document.querySelector<HTMLElement>('.pause-controls')!;
    expect(controls.hidden).toBe(true);

    button('Controls').click();

    expect(controls.hidden).toBe(false);
    expect(button('Controls').getAttribute('aria-expanded')).toBe('true');
    expect([...controls.querySelectorAll('dd')].map((dd) => dd.textContent)).toEqual(
      CONTROLS.map(([, what]) => what),
    );
  });

  it('goes through its buttons by the arrow keys and Tab, and keeps keys from the game', () => {
    opened();
    const game = vi.fn();
    window.addEventListener('keydown', game);

    press(document.activeElement!, 'ArrowDown');
    expect(document.activeElement).toBe(button('Controls'));
    press(document.activeElement!, 'Tab');
    expect(document.activeElement).toBe(button('Exit to menu'));
    press(document.activeElement!, 'ArrowDown');
    expect(document.activeElement).toBe(button('Resume'));
    press(document.activeElement!, 'Tab', { shiftKey: true });
    expect(document.activeElement).toBe(button('Exit to menu'));
    press(document.activeElement!, 'e');

    expect(game).not.toHaveBeenCalled();
    window.removeEventListener('keydown', game);
  });

  it('closes on a click outside it', () => {
    const { menu } = opened();

    document.querySelector('.pause-card')!.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    expect(menu.isOpen).toBe(true);
    document.querySelector('.pause')!.dispatchEvent(new Event('pointerdown', { bubbles: true }));
    expect(menu.isOpen).toBe(false);
  });
});

describe('PauseGate', () => {
  function game() {
    const journal = { isOpen: false, toggle: vi.fn(), close: vi.fn() };
    journal.toggle.mockImplementation(() => (journal.isOpen = !journal.isOpen));
    journal.close.mockImplementation(() => (journal.isOpen = false));
    const gate = new PauseGate(() => journal.isOpen);
    const { menu } = opened();
    menu.close();
    let now = 1000;
    const pause = () => {
      if (gate.allows(now)) menu.open();
    };
    const closed = { toggle: vi.fn(), close: vi.fn() };
    const handler = onGameKey({
      chat: { clear: vi.fn(), cycle: vi.fn() },
      reply: vi.fn(),
      talk: vi.fn(),
      use: vi.fn(),
      view: vi.fn(),
      eat: vi.fn(),
      help: closed,
      journal,
      character: closed,
      log: closed,
      pause,
    });
    window.addEventListener('keydown', handler);
    const frame = (ms: number, update = () => {}) => {
      gate.frameStart();
      update();
      gate.frameEnd(now);
      now += ms;
    };
    const stop = () => window.removeEventListener('keydown', handler);
    return { journal, menu, frame, stop };
  }

  it('opens the menu on a quick second Esc after the player closes the journal', () => {
    const { journal, menu, frame, stop } = game();
    press(document.body, 'j');
    frame(16);
    expect(journal.isOpen).toBe(true);

    press(document.body, 'Escape');
    expect(journal.isOpen).toBe(false);
    expect(menu.isOpen).toBe(false);
    frame(16);
    press(document.body, 'Escape');

    expect(menu.isOpen).toBe(true);
    stop();
  });

  it('ignores Esc just after a panel closes by itself', () => {
    const { journal, menu, frame, stop } = game();
    journal.isOpen = true;
    frame(16, () => (journal.isOpen = false));

    press(document.body, 'Escape');
    expect(menu.isOpen).toBe(false);

    frame(PAUSE_GRACE_MS);
    press(document.body, 'Escape');
    expect(menu.isOpen).toBe(true);
    stop();
  });
});
