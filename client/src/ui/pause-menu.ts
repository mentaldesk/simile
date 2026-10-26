import { CONTROLS } from './help';
import './pause-menu.css';

const kbd = (key: string) => Object.assign(document.createElement('kbd'), { textContent: key });

function button(label: string, onClick: () => void): HTMLButtonElement {
  const made = Object.assign(document.createElement('button'), { type: 'button', textContent: label });
  made.addEventListener('click', onClick);
  return made;
}

/** Esc in game: Resume, the controls, or Exit to the title menu. */
export class PauseMenu {
  private readonly root: HTMLElement;
  private readonly card: HTMLElement;
  private readonly controls: HTMLElement;
  private readonly controlsButton: HTMLButtonElement;
  private readonly resume: HTMLButtonElement;

  constructor(parent: HTMLElement, exit: () => void) {
    this.root = parent.appendChild(document.createElement('div'));
    this.root.className = 'pause';
    this.root.hidden = true;
    this.root.addEventListener('pointerdown', (event) => {
      if (event.target === this.root) this.close();
    });
    this.root.addEventListener('keydown', (event) => this.key(event));

    this.card = this.root.appendChild(document.createElement('section'));
    this.card.className = 'pause-card';
    this.card.tabIndex = -1;
    this.card.setAttribute('role', 'dialog');
    this.card.setAttribute('aria-modal', 'true');
    this.card.ariaLabel = 'Pause menu';
    this.card.appendChild(document.createElement('h2')).textContent = 'Menu';
    const note = this.card.appendChild(document.createElement('p'));
    note.className = 'pause-note';
    note.textContent = 'The village saves itself as you play, and carries on while you’re away.';

    const nav = this.card.appendChild(document.createElement('nav'));
    this.resume = nav.appendChild(button('Resume', () => this.close()));
    this.controlsButton = nav.appendChild(button('Controls', () => this.toggleControls()));
    this.controlsButton.setAttribute('aria-expanded', 'false');
    nav.appendChild(button('Exit to menu', exit));

    this.controls = this.card.appendChild(document.createElement('dl'));
    this.controls.className = 'pause-controls';
    this.controls.hidden = true;
    for (const [keys, what] of CONTROLS) {
      this.controls.appendChild(document.createElement('dt')).append(...keys.map(kbd));
      this.controls.appendChild(document.createElement('dd')).textContent = what;
    }
  }

  get isOpen(): boolean {
    return !this.root.hidden;
  }

  open(): void {
    this.root.hidden = false;
    this.resume.focus();
  }

  close(): void {
    if (!this.isOpen) return;
    this.root.hidden = true;
    this.showControls(false);
    if (this.root.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
  }

  remove(): void {
    this.root.remove();
  }

  private toggleControls(): void {
    this.showControls(this.controls.hidden === true);
  }

  private showControls(shown: boolean): void {
    this.controls.hidden = !shown;
    this.controlsButton.setAttribute('aria-expanded', String(shown));
  }

  // The game's keys mustn't reach it while the menu is open.
  private key(event: KeyboardEvent): void {
    event.stopPropagation();
    const buttons = [...this.card.querySelectorAll('button')];
    const at = buttons.indexOf(document.activeElement as HTMLButtonElement);
    if (event.key === 'Escape') {
      event.preventDefault();
      this.close();
    } else if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      event.preventDefault();
      const step = event.key === 'ArrowDown' ? 1 : -1;
      buttons[(at + step + buttons.length) % buttons.length].focus();
    } else if (event.key === 'Tab') {
      event.preventDefault();
      const step = event.shiftKey ? -1 : 1;
      buttons[(at + step + buttons.length) % buttons.length].focus();
    }
  }
}
