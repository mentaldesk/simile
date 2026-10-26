import type { CharacterPanel } from './character-panel';
import type { ChatBox } from './chat-box';
import { HELP_KEY, type HelpPanel } from './help';
import type { JournalPanel } from './journal-panel';
import { CHARACTER_KEY, EAT_KEY, JOURNAL_KEY, NEWS_KEY, TALK_KEY, VIEW_KEY } from './tuning';

export type GameKeys = {
  chat: Pick<ChatBox, 'open' | 'clear' | 'cycle'>;
  talk: () => void;
  use: () => void;
  view: () => void;
  eat: () => void;
  help: Pick<HelpPanel, 'toggle' | 'close'>;
  journal: Pick<JournalPanel, 'toggle' | 'close'>;
  character: Pick<CharacterPanel, 'toggle' | 'close'>;
};

/** Whether nothing on the page has focus, so a key is the game's and not a link's or a field's. */
export function unfocused({ target }: Event): boolean {
  return (
    !(target instanceof Element) || target === document.body || target === document.documentElement
  );
}

export function onGameKey({ chat, talk, use, view, eat, help, journal, character }: GameKeys): (event: KeyboardEvent) => void {
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
    } else if (pressed(event, TALK_KEY)) {
      // Otherwise the T reaches the chat box once it has focus.
      event.preventDefault();
      talk();
    } else if (pressedNewsKey(event)) {
      event.preventDefault();
      use();
    } else if (pressedViewKey(event)) {
      event.preventDefault();
      view();
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

export function pressedViewKey(event: KeyboardEvent): boolean {
  return pressed(event, VIEW_KEY);
}

function pressed({ key, repeat, ctrlKey, metaKey, altKey }: KeyboardEvent, letter: string): boolean {
  return key.toLowerCase() === letter && !repeat && !(ctrlKey || metaKey || altKey);
}
