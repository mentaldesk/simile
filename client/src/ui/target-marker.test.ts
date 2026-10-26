// @vitest-environment jsdom
import { describe, expect, it } from 'vitest';
import { TargetMarker } from './target-marker';
import type { WorldView } from './world-view';

const view: WorldView = {
  positionOf: () => undefined,
  npcIds: () => ['lachlan'],
  bubbleAnchor: () => undefined,
  spriteOf: () => ({ box: { x: 100, y: 50, width: 20, height: 40 }, depth: 0 }),
};
const nameOf = () => 'Lachlan';
const tag = (root: HTMLElement) => root.querySelector<HTMLElement>('.dialogue-target-name')!;

describe('TargetMarker', () => {
  it('names the ringed resident, and says T talks to them while it does', () => {
    const root = document.createElement('div');
    const marker = new TargetMarker(root);

    marker.render('lachlan', view, nameOf);
    expect(tag(root).textContent).toBe('Lachlan');
    expect(tag(root).classList.contains('dialogue-target-talk')).toBe(false);

    marker.render('lachlan', view, nameOf, true);
    expect(tag(root).ariaLabel).toBe('T: talk to Lachlan');
    expect(tag(root).querySelector('kbd')?.textContent).toBe('T');
    expect(tag(root).classList.contains('dialogue-target-talk')).toBe(true);

    marker.render('lachlan', view, nameOf);
    expect(tag(root).textContent).toBe('Lachlan');
    expect(tag(root).querySelector('kbd')).toBeNull();
  });

  it('hides with nobody ringed', () => {
    const root = document.createElement('div');
    new TargetMarker(root).render(undefined, view, nameOf, true);
    expect(tag(root).hidden).toBe(true);
  });
});
