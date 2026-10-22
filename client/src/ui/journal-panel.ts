import { server, type ClientMessage, type JournalEntry, type JournalMessage, type Lead } from '../net';
import type { Clue } from '../world/clues';
import { callCue } from './call-cue';
import type { HelpPanel } from './help';
import './journal-panel.css';
import { JOURNAL_KEY, NEWS_KEY } from './tuning';

type Server = Pick<typeof server, 'on'>;

/** The last `journal`, for a panel made after it arrives. */
export const journal: { latest?: JournalMessage } = {};
server.on('journal', (message) => (journal.latest = message));

const KEY = JOURNAL_KEY.toUpperCase();
export const EMPTY = 'Nothing yet. Ask around about what happened to Aris.';

/** Sim time is in UTC, so its wall clock is UTC's. */
const LEARNED = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'UTC',
  day: 'numeric',
  month: 'short',
  hour: '2-digit',
  minute: '2-digit',
});

function learnedAt(learned: string): string {
  const time = new Date(learned);
  return Number.isNaN(time.getTime()) ? learned : LEARNED.format(time);
}

/** Every entry's open leads, once each. */
export function openLeads(entries: readonly JournalEntry[]): Lead[] {
  const texts = new Set<string>();
  return entries.flatMap(({ leads }) => leads).filter(({ text }) => !texts.has(text) && texts.add(text));
}

/** "Press E to look at Aris's notes." */
export function cluePrompt(clue: Clue): string {
  return `Press ${NEWS_KEY.toUpperCase()} to look at ${clue.label.replace(/^The /, 'the ')}.`;
}

/** E at a clue: the server finds it, and the journal opens in place of the controls, as J does. */
export function lookAtClue(
  send: (message: ClientMessage) => unknown,
  journal: Pick<JournalPanel, 'open'>,
  help: Pick<HelpPanel, 'close'>,
): void {
  send({ type: 'pick_up' });
  help.close();
  journal.open();
}

/** The player's journal of the incident, opened with J: the open leads, then what they learned, newest first. */
export class JournalPanel {
  readonly hint: HTMLElement;
  private readonly clueHint: HTMLElement;
  private readonly panel: HTMLElement;
  private readonly leads: HTMLElement;
  private readonly entries: HTMLElement;
  private readonly empty: HTMLElement;
  /** How many entries there were when it was last open, or when the first journal came. */
  private seen?: number;
  readonly stop: () => void;

  constructor(parent: HTMLElement, events: Server = server) {
    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'journal-hint';
    this.clueHint = parent.appendChild(document.createElement('div'));
    this.clueHint.className = 'news-hint';
    this.clueHint.hidden = true;
    this.panel = parent.appendChild(document.createElement('section'));
    this.panel.className = 'journal';
    this.panel.ariaLabel = 'Journal';
    this.panel.hidden = true;
    callCue.slot(this.panel);
    const header = this.panel.appendChild(document.createElement('header'));
    header.appendChild(document.createElement('b')).textContent = 'Journal';
    header.appendChild(document.createElement('span')).textContent = `Esc or ${KEY} close`;
    const body = this.panel.appendChild(document.createElement('div'));
    this.leads = body.appendChild(document.createElement('div'));
    this.leads.className = 'journal-leads';
    this.empty = body.appendChild(document.createElement('p'));
    this.empty.className = 'journal-empty';
    this.empty.textContent = EMPTY;
    this.entries = body.appendChild(document.createElement('ol'));
    this.entries.className = 'journal-entries';
    this.seen = journal.latest?.entries.length;
    this.render(journal.latest);
    this.stop = events.on('journal', (message) => this.render(message));
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  toggle(): void {
    this.show(!this.isOpen);
  }

  open(): void {
    this.show(true);
  }

  close(): void {
    this.show(false);
  }

  /** Each frame: says what E does at a clue in reach, unless a panel is open. */
  update(clue: Clue | undefined, shown = true): void {
    this.clueHint.hidden = !clue || !shown || this.isOpen;
    if (clue) this.clueHint.textContent = cluePrompt(clue);
  }

  private show(open: boolean): void {
    this.panel.hidden = !open;
    this.seen = journal.latest?.entries.length;
    this.renderHint(this.seen ?? 0);
  }

  private render(message: JournalMessage | undefined): void {
    const entries = message?.entries ?? [];
    if (this.isOpen || (message && this.seen === undefined)) this.seen = entries.length;
    this.renderHint(entries.length);
    this.empty.hidden = entries.length > 0;
    this.renderLeads(openLeads(entries));
    this.entries.replaceChildren(...[...entries].reverse().map((entry) => this.entry(entry)));
  }

  private renderHint(count: number): void {
    this.hint.hidden = this.isOpen;
    const fresh = count - (this.seen ?? count);
    const kbd = Object.assign(document.createElement('kbd'), { textContent: KEY });
    this.hint.replaceChildren(kbd, fresh > 0 ? ` journal · ${fresh} new` : ' journal');
    this.hint.classList.toggle('journal-hint-new', fresh > 0);
  }

  private renderLeads(leads: readonly Lead[]): void {
    this.leads.hidden = leads.length === 0;
    const title = Object.assign(document.createElement('b'), { textContent: 'Leads' });
    const list = document.createElement('ul');
    list.append(...leads.map(({ text }) => Object.assign(document.createElement('li'), { textContent: text })));
    this.leads.replaceChildren(title, list);
  }

  private entry({ text, source, learned, flushed }: JournalEntry): HTMLElement {
    const item = document.createElement('li');
    item.classList.toggle('journal-flushed', flushed === true);
    item.appendChild(document.createElement('p')).textContent = text;
    const from = item.appendChild(document.createElement('small'));
    from.textContent = `${source.name} · ${learnedAt(learned)}`;
    if (flushed === true) {
      const mark = from.appendChild(document.createElement('span'));
      mark.className = 'journal-flush';
      mark.textContent = 'flushed';
      mark.title = 'Your eye caught them flush as they said it.';
    }
    return item;
  }
}
