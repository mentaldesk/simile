import { describe, expect, it } from 'vitest';
import { toCanvas } from './view';

const VIEW = { width: 1600, height: 1000 };

describe('toCanvas', () => {
  it('puts the point the camera centres on at the middle of the canvas', () => {
    const scroll = { x: 200 - VIEW.width / 2, y: -300 - VIEW.height / 2 };
    expect(toCanvas({ x: 200, y: -300 }, scroll, VIEW, 2)).toEqual({ x: 800, y: 500 });
  });

  it('zooms about the middle of the canvas', () => {
    const scroll = { x: -VIEW.width / 2, y: -VIEW.height / 2 };
    expect(toCanvas({ x: 10, y: -20 }, scroll, VIEW, 3)).toEqual({ x: 830, y: 440 });
  });
});
