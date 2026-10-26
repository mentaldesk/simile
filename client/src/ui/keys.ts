import type { Reachable, WayPrompt } from '../world/reach';
import type { CharacterPanel } from './character-panel';
import type { ChatBox } from './chat-box';
import { HELP_KEY, type HelpPanel } from './help';
import type { JournalPanel } from './journal-panel';
import { CHARACTER_KEY, EAT_KEY, JOURNAL_KEY, NEWS_KEY } from './tuning';

export type GameKeys = {
  chat: Pick<ChatBox, 'open' | 'clear' | 'cycle'>;
  use: () => void;
  eat: () => void;
  help: Pick<HelpPanel, 'toggle' | 'close'>;
  journal: Pick<JournalPanel, 'toggle' | 'close'>;
  character: Pick<CharacterPanel, 'toggle' | 'close'>;
};

export type EUse = { kind: 'reach'; reachable: Reachable } | { kind: 'door' } | { kind: 'talk'; npcId: string };

/** What E does: uses the nearest thing in reach, else the world scene takes a door, else talks to the ringed resident. */
export function eUse(reachable: Reachable | undefined, ways: readonly WayPrompt[], ringed: string | undefined): EUse | undefined {
  if (reachable) return { kind: 'reach', reachable };
  if (ways.some(({ keys }) => keys.includes('E'))) return { kind: 'door' };
  return ringed === undefined ? undefined : { kind: 'talk', npcId: ringed };
}

/** Whether nothing on the page has focus, so a key is the game's and not a link's or a field's. */
export function unfocused({ target }: Event): boolean {
  return (
    !(target instanceof Element) || target === document.body || target === document.documentElement
  );
}

export function onGameKey({ chat, use, eat, help, journal, character }: GameKeys): (event: KeyboardEvent) => void {
  return (event) => {
    if (!unfocused(event)) return;
    const { key } = event;
    if (key === 'Enter') {
      // Otherwise the same Enter reaches the input once it has focus, and sends nothing.
      event.preventDefault();
      chat.open();
    } else if (key === 'Escape') {
      chat.clear();
      help.close();
      journal.close();
      character.close();
    } else if (key === HELP_KEY && !event.repeat) {
      event.preventDefault();
      journal.close();
      character.close();
      help.toggle();
    } else if (key === 'Tab') {
      event.preventDefault();
      chat.cycle(event.shiftKey ? -1 : 1);
    } else if (pressedNewsKey(event)) {
      event.preventDefault();
      use();
    } else if (pressed(event, EAT_KEY)) {
      event.preventDefault();
      eat();
    } else if (pressed(event, JOURNAL_KEY)) {
      event.preventDefault();
      help.close();
      character.close();
      journal.toggle();
    } else if (pressed(event, CHARACTER_KEY)) {
      event.preventDefault();
      help.close();
      journal.close();
      character.toggle();
    }
  };
}

export function pressedNewsKey(event: KeyboardEvent): boolean {
  return pressed(event, NEWS_KEY);
}

function pressed({ key, repeat, ctrlKey, metaKey, altKey }: KeyboardEvent, letter: string): boolean {
  return key.toLowerCase() === letter && !repeat && !(ctrlKey || metaKey || altKey);
}
