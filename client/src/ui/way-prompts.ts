import type { WayPrompt } from '../world/reach';

const MARGIN = 2;
const GAP = 3;

const clamp = (value: number, min: number, max: number) => Math.min(Math.max(value, min), max);

/** A small tag over each door, stairs, ladder or lift the player can take, naming its keys and what it does. */
export class WayPromptLayer {
  private readonly root: HTMLElement;
  private readonly tags: HTMLElement[] = [];

  constructor(parent: HTMLElement) {
    this.root = parent.appendChild(document.createElement('div'));
    this.root.className = 'way-prompts';
  }

  /** `fromGame` takes game-canvas px to overlay px. Tags that would overlap are moved apart along the row. */
  render(prompts: readonly WayPrompt[], fromGame: number): void {
    const placed = prompts.map((prompt, i) => {
      const tag = this.tags[i] ?? this.add();
      const text = `${prompt.keys.join(' ')}: ${prompt.action}`;
      if (tag.ariaLabel !== text) fill(tag, prompt, text);
      tag.hidden = false;
      const { offsetWidth: width, offsetHeight: height } = tag;
      return { tag, width, left: prompt.x * fromGame - width / 2, top: prompt.y * fromGame - height, height };
    });
    placed.sort((a, b) => a.left - b.left);
    const wanted = placed.reduce((sum, { left }) => sum + left, 0);
    placed.forEach((one, i) => {
      if (i > 0) one.left = Math.max(one.left, placed[i - 1].left + placed[i - 1].width + GAP);
    });
    const shift = (wanted - placed.reduce((sum, { left }) => sum + left, 0)) / Math.max(placed.length, 1);
    for (const { tag, width, height, left, top } of placed) {
      const x = clamp(left + shift, MARGIN, this.root.offsetWidth - width - MARGIN);
      const y = clamp(top, MARGIN, this.root.offsetHeight - height - MARGIN);
      tag.style.transform = `translate(${Math.round(x)}px, ${Math.round(y)}px)`;
    }
    for (const tag of this.tags.slice(prompts.length)) tag.hidden = true;
  }

  private add(): HTMLElement {
    const tag = this.root.appendChild(document.createElement('div'));
    tag.className = 'way-prompt';
    this.tags.push(tag);
    return tag;
  }
}

function fill(tag: HTMLElement, { keys, action }: WayPrompt, text: string): void {
  tag.ariaLabel = text;
  tag.replaceChildren(
    ...keys.map((key) => Object.assign(document.createElement('kbd'), { textContent: key })),
    Object.assign(document.createElement('span'), { textContent: action }),
  );
}
