import type { Position } from '../../net';
import type { ScreenBox } from '../../ui/world-view';
import { toCanvas, type Size } from '../view';
import type { Figure } from './cutaway';
import { residentDepth } from './depth';
import type { IsoTile } from './manifest';
import { feetOf, project } from './projection';
import { FIGURE_HEIGHT, FIGURE_WIDTH } from './tuning';

export type IsoCamera = Size & { scrollX: number; scrollY: number; zoom: number };

export function figureAt(
  position: Position,
  tile: IsoTile,
  heightAt: (position: Position) => number,
): Figure {
  const feet = feetOf(position);
  const screen = project(tile, feet, heightAt(position));
  return {
    x: screen.x,
    top: screen.y - FIGURE_HEIGHT,
    bottom: screen.y,
    depth: residentDepth(feet, tile),
  };
}

/** Where a figure's sprite is drawn on the canvas, after the camera's scroll and zoom. */
export function figureBox(figure: Figure, camera: IsoCamera): ScreenBox {
  const scroll = { x: camera.scrollX, y: camera.scrollY };
  const top = toCanvas({ x: figure.x, y: figure.top }, scroll, camera, camera.zoom);
  const width = FIGURE_WIDTH * camera.zoom;
  const height = (figure.bottom - figure.top) * camera.zoom;
  return { x: top.x - width / 2, y: top.y, width, height };
}

/** Turned 45° so x runs left to right on screen, which audio pans by. Distances don't change. */
export function screenAligned(position: Position | undefined): Position | undefined {
  if (!position) return undefined;
  const { x, y } = position;
  return { x: (x - y) / Math.SQRT2, y: (x + y) / Math.SQRT2 };
}
