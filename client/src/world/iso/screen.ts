import type { Position } from '../../net';
import type { ScreenBox } from '../../ui/world-view';
import { toCanvas, type Size } from '../view';
import type { Figure } from './cutaway';
import { residentDepth } from './depth';
import type { IsoTile } from './manifest';
import { feetOf, project } from './projection';

export type IsoCamera = Size & { scrollX: number; scrollY: number; zoom: number };

/** A character sprite's frame as drawn, in scene px: texture px times the sprite's scale. */
export type SpriteFrame = {
  width: number;
  height: number;
  /** The feet, from the frame's top left. */
  anchor: { x: number; y: number };
  /** From the feet to the top of the head. */
  figureHeight: number;
};

export function figureAt(
  position: Position,
  tile: IsoTile,
  heightAt: (position: Position) => number,
  frame: SpriteFrame,
): Figure {
  const feet = feetOf(position);
  const screen = project(tile, feet, heightAt(position));
  return {
    x: screen.x,
    top: screen.y - frame.figureHeight,
    bottom: screen.y,
    depth: residentDepth(feet, tile),
  };
}

/** The sprite's frame down to the feet, on the canvas: the UI rings its bottom edge. */
export function figureBox(figure: Figure, camera: IsoCamera, frame: SpriteFrame): ScreenBox {
  const scroll = { x: camera.scrollX, y: camera.scrollY };
  const corner = { x: figure.x - frame.anchor.x, y: figure.bottom - frame.anchor.y };
  const { x, y } = toCanvas(corner, scroll, camera, camera.zoom);
  return { x, y, width: frame.width * camera.zoom, height: frame.anchor.y * camera.zoom };
}

/** Turned 45° so x runs left to right on screen, which audio pans by. Distances don't change. */
export function screenAligned(position: Position | undefined): Position | undefined {
  if (!position) return undefined;
  const { x, y } = position;
  return { ...position, x: (x - y) / Math.SQRT2, y: (x + y) / Math.SQRT2 };
}
