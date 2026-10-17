import type { Size } from '../world/view';
import type { ScreenBox, ScreenPoint, WorldView } from './world-view';

export const OVERLAY_SIZE = { width: 640, height: 360 };

export type OverlayFit = { scale: number; width: number; height: number; fromGame: number };

/** Lays the overlay out at least 640 × 360 px and scales it to cover the canvas. */
export function fitOverlay(canvas: Size, game: Size): OverlayFit {
  const fit = Math.min(canvas.width / OVERLAY_SIZE.width, canvas.height / OVERLAY_SIZE.height);
  const scale = Math.max(1, fit);
  return {
    scale,
    width: Math.round(canvas.width / scale),
    height: Math.round(canvas.height / scale),
    fromGame: canvas.width / game.width / scale,
  };
}

export function inOverlay(view: WorldView, fromGame: number): WorldView {
  const point = ({ x, y }: ScreenPoint): ScreenPoint => ({ x: x * fromGame, y: y * fromGame });
  const box = ({ x, y, width, height }: ScreenBox): ScreenBox => ({
    ...point({ x, y }),
    width: width * fromGame,
    height: height * fromGame,
  });
  return {
    positionOf: (id) => view.positionOf(id),
    npcIds: () => view.npcIds(),
    bubbleAnchor: (id) => {
      const anchor = view.bubbleAnchor(id);
      return anchor && point(anchor);
    },
    spriteOf: (id) => {
      const sprite = view.spriteOf(id);
      return sprite && { box: box(sprite.box), depth: sprite.depth };
    },
  };
}
