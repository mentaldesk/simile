import { bubbleAlpha, type Bubble } from './bubbles';
import { distanceFromPlayer, type WorldView } from './world-view';

const MARGIN = 2;
const TAIL = 4;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

export class BubbleLayer {
  private readonly root: HTMLElement;
  private readonly elements = new Map<string, HTMLElement>();

  constructor(parent: HTMLElement) {
    this.root = parent.appendChild(document.createElement('div'));
    this.root.className = 'dialogue-bubbles';
  }

  render(bubbles: readonly Bubble[], view: WorldView, now = Date.now()): void {
    const shown = new Set<string>();
    for (const bubble of bubbles) {
      const anchor = view.bubbleAnchor(bubble.speaker);
      const distance = distanceFromPlayer(view, bubble.speaker);
      const alpha = anchor && distance !== undefined ? bubbleAlpha(bubble, distance, now) : 0;
      if (!anchor || alpha === 0) continue;

      shown.add(bubble.speaker);
      const element = this.element(bubble.speaker);
      if (element.textContent !== bubble.text) element.textContent = bubble.text;
      const { offsetWidth: width, offsetHeight: height } = element;
      const left = clamp(anchor.x - width / 2, MARGIN, this.root.offsetWidth - width - MARGIN);
      const top = clamp(anchor.y - height - TAIL, MARGIN, this.root.offsetHeight - height - MARGIN);
      element.style.transform = `translate(${Math.round(left)}px, ${Math.round(top)}px)`;
      element.style.opacity = alpha.toFixed(2);
      element.style.setProperty(
        '--tail-x',
        `${Math.round(clamp(anchor.x - left, TAIL, width - TAIL))}px`,
      );
    }
    for (const [speaker, element] of this.elements) {
      if (shown.has(speaker)) continue;
      element.remove();
      this.elements.delete(speaker);
    }
  }

  private element(speaker: string): HTMLElement {
    let element = this.elements.get(speaker);
    if (!element) {
      element = this.root.appendChild(document.createElement('div'));
      element.className = 'dialogue-bubble';
      this.elements.set(speaker, element);
    }
    return element;
  }
}
