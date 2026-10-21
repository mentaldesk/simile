import type { ChatBox } from './chat-box';
import { HELP_KEY, type HelpPanel } from './help';
import { NEWS_KEY } from './tuning';

export type GameKeys = {
  chat: Pick<ChatBox, 'open' | 'clear' | 'cycle'>;
  news: () => void;
  help: Pick<HelpPanel, 'toggle' | 'close'>;
};

/** Whether nothing on the page has focus, so a key is the game's and not a link's or a field's. */
export function unfocused({ target }: Event): boolean {
  return (
    !(target instanceof Element) || target === document.body || target === document.documentElement
  );
}

export function onGameKey({ chat, news, help }: GameKeys): (event: KeyboardEvent) => void {
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
    } else if (key === HELP_KEY && !event.repeat) {
      event.preventDefault();
      help.toggle();
    } else if (key === 'Tab') {
      event.preventDefault();
      chat.cycle(event.shiftKey ? -1 : 1);
    } else if (pressedNewsKey(event)) {
      event.preventDefault();
      news();
    }
  };
}

export function pressedNewsKey({ key, repeat, ctrlKey, metaKey, altKey }: KeyboardEvent): boolean {
  return key.toLowerCase() === NEWS_KEY && !repeat && !(ctrlKey || metaKey || altKey);
}
