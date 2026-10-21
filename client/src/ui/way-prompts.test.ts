// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { WayPromptLayer } from './way-prompts';

const shown = (root: HTMLElement) =>
  [...root.querySelectorAll<HTMLElement>('.way-prompt')]
    .filter((tag) => !tag.hidden)
    .map((tag) => [...tag.querySelectorAll('kbd')].map((key) => key.textContent).join('+') + ' ' + tag.querySelector('span')?.textContent);

describe('WayPromptLayer', () => {
  it('shows a tag naming the keys and what they do for each prompt', () => {
    const root = document.createElement('div');
    const layer = new WayPromptLayer(root);
    layer.render(
      [
        { keys: ['E'], action: 'go out', x: 100, y: 50 },
        { keys: ['↑', '↓'], action: 'lift', x: 110, y: 50 },
      ],
      0.5,
    );
    expect(shown(root)).toEqual(['E go out', '↑+↓ lift']);
    expect(root.querySelectorAll('.way-prompt')[1]?.ariaLabel).toBe('↑ ↓: lift');
  });

  it('hides the tags it no longer needs, and reuses them', () => {
    const root = document.createElement('div');
    const layer = new WayPromptLayer(root);
    layer.render([{ keys: ['E'], action: 'go out', x: 0, y: 0 }, { keys: ['↓'], action: 'downstairs', x: 0, y: 0 }], 1);
    layer.render([{ keys: ['↑'], action: 'upstairs', x: 0, y: 0 }], 1);
    expect(shown(root)).toEqual(['↑ upstairs']);
    layer.render([], 1);
    expect(shown(root)).toEqual([]);
    expect(root.querySelectorAll('.way-prompt')).toHaveLength(2);
  });
});
