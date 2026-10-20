import { describe, expect, it } from 'vitest';
import {
  FEET_AT,
  follow,
  FOOTROOM,
  HEADROOM,
  layerCopies,
  MIN_VIEW_WIDTH_M,
  sideZoom,
  streetCentreY,
  viewCentre,
  VIEW_HEIGHT_M,
} from './camera';
import { PPM } from './layout';

describe('the side camera', () => {
  it('shows the street VIEW_HEIGHT_M tall, or MIN_VIEW_WIDTH_M wide in a narrow window', () => {
    for (const canvas of [
      { width: 2880, height: 1800 },
      { width: 1280, height: 720 },
      { width: 5120, height: 2880 },
    ]) {
      expect(canvas.height / sideZoom(canvas) / PPM).toBeCloseTo(VIEW_HEIGHT_M);
    }
    const portrait = { width: 750, height: 1624 };
    expect(portrait.width / sideZoom(portrait) / PPM).toBeCloseTo(MIN_VIEW_WIDTH_M);
  });

  const view = { width: 3000, height: VIEW_HEIGHT_M * PPM };
  const feet = 2112;

  it('follows the player along the street and stops at its ends', () => {
    const out = { x: 0, y: 0 };
    expect(viewCentre({ x: 5000, y: feet }, feet, 11088, view, out).x).toBe(5000);
    expect(viewCentre({ x: 100, y: feet }, feet, 11088, view, out).x).toBe(1500);
    expect(viewCentre({ x: 11000, y: feet }, feet, 11088, view, out).x).toBe(11088 - 1500);
    expect(viewCentre({ x: 100, y: feet }, feet, 2000, view, out).x).toBe(1000);
  });

  it('keeps the street low in the view, and rises when the player climbs high', () => {
    const out = { x: 0, y: 0 };
    viewCentre({ x: 5000, y: feet }, feet, 11088, view, out);
    expect(feet - (out.y - view.height / 2)).toBeCloseTo(FEET_AT * view.height);
    expect(out.y).toBeCloseTo(streetCentreY(feet, view));
    const high = feet - 11 * PPM;
    viewCentre({ x: 5000, y: high }, feet, 11088, view, out);
    expect(high - (out.y - view.height / 2)).toBeCloseTo(HEADROOM * view.height);
    const river = feet + 3.3 * PPM;
    viewCentre({ x: 5000, y: river }, feet, 11088, view, out);
    expect(river - (out.y - view.height / 2)).toBeCloseTo(FOOTROOM * view.height);
  });

  it('eases towards its target whatever the frame rate', () => {
    const at = (steps: number) => {
      let current = { x: 0, y: 0 };
      for (let i = 0; i < steps; i++) current = follow(current, { x: 100, y: 0 }, 1 / steps, { x: 0, y: 0 });
      return current.x;
    };
    expect(at(30)).toBeCloseTo(at(120), 6);
    expect(at(60)).toBeGreaterThan(99);
  });
});

describe('parallax', () => {
  const centre = { x: 4000, y: 1500 };
  const view = { left: 2500, width: 3000, centre };

  it('covers the view with copies of a layer', () => {
    for (const parallax of [0.04, 0.2, 0.45, 0.85, 1, 1.3]) {
      const copies = layerCopies(parallax, 1316, view, 0, 1500, { first: 0, count: 0, y: 0 });
      expect(copies.first).toBeLessThanOrEqual(view.left);
      expect(copies.first + copies.count * 1316).toBeGreaterThanOrEqual(view.left + view.width);
    }
  });

  it('moves each layer that share of the way the camera moves', () => {
    for (const parallax of [0.2, 0.45, 1, 1.3]) {
      const before = layerCopies(parallax, 1000, view, 0, 1500, { first: 0, count: 0, y: 0 }).first;
      const moved = { left: view.left + 10, width: view.width, centre: { x: centre.x + 10, y: centre.y } };
      const after = layerCopies(parallax, 1000, moved, 0, 1500, { first: 0, count: 0, y: 0 }).first;
      const onScreen = (after - moved.left - (before - view.left) + 1000 * 10) % 1000;
      expect(onScreen).toBeCloseTo((10 * (1 - parallax) - 10 + 1000 * 10) % 1000);
    }
  });

  it('rises less than the camera for distant layers', () => {
    const up = { ...view, centre: { x: centre.x, y: centre.y - 400 } };
    expect(layerCopies(0.2, 1000, up, 100, 1500, { first: 0, count: 0, y: 0 }).y).toBeCloseTo(100 - 320);
    expect(layerCopies(1, 1000, up, 100, 1500, { first: 0, count: 0, y: 0 }).y).toBe(100);
    expect(layerCopies(1.3, 1000, up, 100, 1500, { first: 0, count: 0, y: 0 }).y).toBe(100);
  });
});
