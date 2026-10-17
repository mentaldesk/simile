import type { ScreenBox, ScreenPoint, ScreenSprite, WorldView } from '../ui/world-view';
import type { Point, Size } from './view';

export type Box = ScreenBox;

/** The NPC at a canvas point: front to back, the first opaque there, else the first box there. */
export function npcAt(point: ScreenPoint, view: WorldView): string | undefined {
  const hits: (ScreenSprite & { id: string })[] = [];
  for (const id of view.npcIds()) {
    const sprite = view.spriteOf(id);
    if (sprite && contains(sprite.box, point)) hits.push({ id, ...sprite });
  }
  hits.sort((a, b) => b.depth - a.depth);
  return (hits.find((hit) => hit.opaqueAt?.(point)) ?? hits[0])?.id;
}

export function framePixel(point: ScreenPoint, box: Box, frame: Size): Point {
  return {
    x: Math.floor(((point.x - box.x) * frame.width) / box.width),
    y: Math.floor(((point.y - box.y) * frame.height) / box.height),
  };
}

function contains(box: Box, { x, y }: ScreenPoint): boolean {
  return x >= box.x && x < box.x + box.width && y >= box.y && y < box.y + box.height;
}
