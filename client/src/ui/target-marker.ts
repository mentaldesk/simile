import type { WorldView } from './world-view';

const tag = (name: string, text: string) => Object.assign(document.createElement(name), { textContent: text });

export class TargetMarker {
  private readonly ring: HTMLElement;
  private readonly name: HTMLElement;

  constructor(parent: HTMLElement) {
    this.ring = parent.appendChild(document.createElement('div'));
    this.ring.className = 'dialogue-target-ring';
    this.name = parent.appendChild(document.createElement('div'));
    this.name.className = 'dialogue-target-name';
    this.ring.hidden = this.name.hidden = true;
  }

  /** With `talks`, the name says E talks to them, as the way tags name their keys. */
  render(npcId: string | undefined, view: WorldView, nameOf: (id: string) => string, talks = false): void {
    const box = npcId === undefined ? undefined : view.spriteOf(npcId)?.box;
    this.ring.hidden = this.name.hidden = !box;
    if (!box || npcId === undefined) return;
    const name = nameOf(npcId);
    const label = talks ? `E: talk to ${name}` : name;
    if (this.name.ariaLabel !== label) {
      this.name.ariaLabel = label;
      this.name.classList.toggle('dialogue-target-talk', talks);
      this.name.replaceChildren(...(talks ? [tag('kbd', 'E'), tag('span', `talk to ${name}`)] : [name]));
    }
    const x = Math.round(box.x + box.width / 2);
    const feet = Math.round(box.y + box.height);
    this.ring.style.transform = `translate(${x}px, ${feet}px) translate(-50%, -75%)`;
    this.name.style.transform = `translate(${x}px, ${Math.round(box.y)}px) translate(-50%, -100%)`;
  }
}
