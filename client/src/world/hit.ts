import type { ScreenPoint, WorldView } from '../ui/world-view';
import { SPRITE_HEIGHT, TILE_SIZE, ZOOM } from './tuning';

export type Box = { x: number; y: number; width: number; height: number };

const WIDTH = TILE_SIZE * ZOOM;
const HEIGHT = SPRITE_HEIGHT * ZOOM;

/** The canvas box an entity's sprite covers, below the top centre its bubble is pinned to. */
export function spriteBox(entityId: string, view: WorldView): Box | undefined {
  const anchor = view.bubbleAnchor(entityId);
  return anchor && { x: anchor.x - WIDTH / 2, y: anchor.y, width: WIDTH, height: HEIGHT };
}

/** The NPC drawn at a canvas point: the one in front where sprites overlap. */
export function npcAt(point: ScreenPoint, view: WorldView): string | undefined {
  let front: { id: string; box: Box } | undefined;
  for (const id of view.npcIds()) {
    const box = spriteBox(id, view);
    if (box && contains(box, point) && (!front || box.y > front.box.y)) front = { id, box };
  }
  return front?.id;
}

function contains(box: Box, { x, y }: ScreenPoint): boolean {
  return x >= box.x && x < box.x + box.width && y >= box.y && y < box.y + box.height;
}
