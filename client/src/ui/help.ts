import { callCue } from './call-cue';

/** Shows and hides the controls. */
export const HELP_KEY = '?';

/** The game's keys and what they do, as the help lists them: each key, or either. */
export const CONTROLS: readonly (readonly [keys: readonly string[], what: string])[] = [
  [['← →', 'A D'], 'walk'],
  [['Shift'], 'hold to run'],
  [['↑', 'W'], 'upstairs or up a ladder from beside its foot, or the lift up'],
  [['↓', 'S'], 'downstairs or down a ladder from beside its top, or the lift down'],
  [['E'], 'read the news at a terminal, look at a mural or a painting, order at a counter, go through a door, or talk to the ringed resident'],
  [['Enter'], 'talk to the ringed resident, then send'],
  [['Tab'], 'choose who to talk to'],
  [['Esc'], 'close the chat or a panel'],
  [[HELP_KEY], 'show or hide the controls'],
];

const NOTE = 'A tag over each door, flight, ladder and lift names its keys. Where E is used for something else, ↑ takes the door.';

/** What the help says about voices, as the top-level README does. */
export const VOICES =
  'Residents talk in speech bubbles unless the village was started with SIMILE_VOICE=1 ./run.sh, on a Mac with Apple Silicon. Either way, each greets you out loud when they start talking to you.';

const kbd = (key: string) => Object.assign(document.createElement('kbd'), { textContent: key });

/** "? controls" in a corner, and the controls themselves while it's open. */
export class HelpPanel {
  private readonly hint: HTMLElement;
  private readonly panel: HTMLElement;

  constructor(parent: HTMLElement) {
    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'help-hint';
    this.hint.append(kbd(HELP_KEY), ' controls');
    this.panel = parent.appendChild(document.createElement('section'));
    this.panel.className = 'help';
    this.panel.ariaLabel = 'Controls';
    this.panel.hidden = true;
    callCue.slot(this.panel);
    this.panel.appendChild(document.createElement('b')).textContent = 'Controls';
    const list = this.panel.appendChild(document.createElement('dl'));
    for (const [keys, what] of CONTROLS) {
      list.appendChild(document.createElement('dt')).append(...keys.map(kbd));
      list.appendChild(document.createElement('dd')).textContent = what;
    }
    this.panel.appendChild(document.createElement('p')).textContent = NOTE;
    this.panel.appendChild(document.createElement('p')).textContent = VOICES;
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  toggle(): void {
    this.show(!this.isOpen);
  }

  close(): void {
    this.show(false);
  }

  private show(open: boolean): void {
    this.panel.hidden = !open;
    this.hint.hidden = open;
  }
}
