import type { CharacterPanel } from './character-panel';
import type { ChatBox } from './chat-box';
import { HELP_KEY, type HelpPanel } from './help';
import type { JournalPanel } from './journal-panel';
import type { LogPanel } from './log-panel';
import { CHARACTER_KEY, EAT_KEY, JOURNAL_KEY, NEWS_KEY, TALK_KEY, VIEW_KEY } from './tuning';

export type GameKeys = {
  chat: Pick<ChatBox, 'clear' | 'cycle'>;
  reply: () => void;
  talk: () => void;
  use: () => void;
  view: () => void;
  eat: () => void;
  help: Pick<HelpPanel, 'toggle' | 'close'>;
  journal: Pick<JournalPanel, 'toggle' | 'close'>;
  character: Pick<CharacterPanel, 'toggle' | 'close'>;
  log: Pick<LogPanel, 'close'>;
  pause: () => void;
};

export type Talker = {
  chat: Pick<ChatBox, 'choose' | 'open'>;
  log: Pick<LogPanel, 'isReading' | 'toggle' | 'close'>;
  ringed: () => string | undefined;
};

/** Enter talks to the ringed resident; with nobody to talk to, it opens the log to read, or closes it. */
export function reply({ chat, log, ringed }: Talker): void {
  if (log.isReading || ringed() === undefined) log.toggle();
  else chat.open();
}

/** T orders from whoever serves at the counter the player is at, else does as Enter does. */
export function talk(talker: Talker, counter: { serving: string | undefined } | undefined): void {
  if (!counter) return reply(talker);
  talker.log.close();
  if (counter.serving) talker.chat.choose(counter.serving);
  talker.chat.open();
}

/** Whether nothing on the page has focus, so a key is the game's and not a link's or a field's. */
export function unfocused({ target }: Event): boolean {
  return (
    !(target instanceof Element) || target === document.body || target === document.documentElement
  );
}

export function onGameKey({ chat, reply, talk, use, view, eat, help, journal, character, log, pause }: GameKeys): (event: KeyboardEvent) => void {
  return (event) => {
    if (!unfocused(event)) return;
    const { key } = event;
    if (key === 'Enter') {
      // Otherwise the same Enter reaches the input once it has focus, and sends nothing.
      event.preventDefault();
      reply();
    } else if (key === 'Escape') {
      pause();
      chat.clear();
      help.close();
      journal.close();
      character.close();
      log.close();
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
