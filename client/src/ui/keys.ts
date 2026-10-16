import type { ChatBox } from './chat-box';
import { NEWS_KEY } from './tuning';

export type GameKeys = {
  chat: Pick<ChatBox, 'open' | 'clear' | 'cycle'>;
  news: () => void;
};

/** Whether nothing on the page has focus, so a key is the game's and not a link's or a field's. */
export function unfocused({ target }: Event): boolean {
  return (
    !(target instanceof Element) || target === document.body || target === document.documentElement
  );
}

export function onGameKey({ chat, news }: GameKeys): (event: KeyboardEvent) => void {
  return (event) => {
    if (!unfocused(event)) return;
    const { key } = event;
    if (key === 'Enter') {
      // Otherwise the same Enter reaches the input once it has focus, and sends nothing.
      event.preventDefault();
      chat.open();
    } else if (key === 'Escape') {
      chat.clear();
    } else if (key === 'Tab') {
      event.preventDefault();
      chat.cycle(event.shiftKey ? -1 : 1);
    } else if (key.toLowerCase() === NEWS_KEY && !event.repeat && !modified(event)) {
      event.preventDefault();
      news();
    }
  };
}

function modified({ ctrlKey, metaKey, altKey }: KeyboardEvent): boolean {
  return ctrlKey || metaKey || altKey;
}
