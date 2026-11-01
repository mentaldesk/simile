import { callCue } from './call-cue';

/** Shows and hides the controls. */
export const HELP_KEY = '?';

/** The game's keys and what they do, as the help lists them: each key, or either. */
export const CONTROLS: readonly (readonly [keys: readonly string[], what: string])[] = [
  [['← →', 'A D'], 'walk, or steer in the air'],
  [['Shift'], 'switch between walking and running, until pressed again'],
  [['Space'], 'jump, higher while held and further running; land on a rat to kill it'],
  [['↑', 'W'], 'upstairs or up a ladder from beside its foot, or the lift up; on a ladder, Space jumps off it'],
  [['↓', 'S'], 'downstairs or down a ladder from beside its top, or the lift down'],
  [['E'], 'go through a door or onto another street; off a door, read the news at a terminal, pick something up, sell salvage, trade at the clinic, look at a clue, or use a machine with the datajack'],
  [['T'], 'talk to the ringed resident, or at a counter order from whoever serves there; with nobody near, open or close the conversation log'],
  [['V'], 'look at a mural or a painting'],
  [['F'], 'eat: a meal at home, at the café or the noodle bar, or food you carry'],
  [['J'], 'open or close your journal: what you have learned about Aris, and the leads still open'],
  [['L'], 'switch your lamp on or off, to see in the dark; stand at a plug to charge it'],
  [['C'], 'open or close your character: your vitals, your body, what you carry and the recipes you know'],
  [['Enter'], 'talk to the ringed resident, then send; with nobody near, open or close the conversation log'],
  [['Tab'], 'choose who to talk to'],
  [['Esc'], 'close the chat or a panel; with none open, open the menu'],
  [[HELP_KEY], 'show or hide the controls'],
];

const NOTE = 'A tag over each door, flight, ladder and lift names its keys.';

/** What the help says about healing, as the top-level README does. */
export const REST = 'Hurt? Stand at your bed, up the ladder in the maker space, to heal fast.';

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
    this.panel.appendChild(document.createElement('p')).textContent = REST;
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
