import type { WorldView } from './world-view';

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

  render(npcId: string | undefined, view: WorldView, nameOf: (id: string) => string): void {
    const box = npcId === undefined ? undefined : view.spriteOf(npcId)?.box;
    this.ring.hidden = this.name.hidden = !box;
    if (!box || npcId === undefined) return;
    const name = nameOf(npcId);
    if (this.name.textContent !== name) this.name.textContent = name;
    const x = Math.round(box.x + box.width / 2);
    const feet = Math.round(box.y + box.height);
    this.ring.style.transform = `translate(${x}px, ${feet}px) translate(-50%, -75%)`;
    this.name.style.transform = `translate(${x}px, ${Math.round(box.y)}px) translate(-50%, -100%)`;
  }
}
