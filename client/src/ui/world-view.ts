import { server, type Entity, type Position } from '../net';

export const PLAYER_ID = 'player';

export type ScreenPoint = { x: number; y: number };

/** What the dialogue UI needs from the world scene. README.md describes it. */
export interface WorldView {
  positionOf(entityId: string): Position | undefined;
  npcIds(): Iterable<string>;
  bubbleAnchor(entityId: string): ScreenPoint | undefined;
}

export const TILE_PX = 48;
const SPRITE_HEIGHT_PX = 72;

export class TrackedWorld implements WorldView {
  viewport = { width: 640, height: 360 };
  private readonly entities = new Map<string, Entity>();

  reset(entities: readonly Entity[]): void {
    this.entities.clear();
    for (const entity of entities) this.entities.set(entity.id, entity);
  }

  move(entityId: string, position: Position): void {
    const entity = this.entities.get(entityId);
    if (entity) this.entities.set(entityId, { ...entity, position });
  }

  all(): Entity[] {
    return [...this.entities.values()];
  }

  positionOf(entityId: string): Position | undefined {
    return this.entities.get(entityId)?.position;
  }

  *npcIds(): Iterable<string> {
    for (const { id, kind } of this.entities.values()) if (kind === 'npc') yield id;
  }

  feetOnScreen(position: Position): ScreenPoint | undefined {
    const player = this.positionOf(PLAYER_ID);
    if (!player) return undefined;
    return {
      x: this.viewport.width / 2 + (position.x - player.x) * TILE_PX,
      y: this.viewport.height / 2 + (position.y - player.y + 0.5) * TILE_PX,
    };
  }

  tileAt(point: ScreenPoint): Position | undefined {
    const player = this.positionOf(PLAYER_ID);
    if (!player) return undefined;
    return {
      x: Math.round(player.x + (point.x - this.viewport.width / 2) / TILE_PX),
      y: Math.round(player.y + (point.y - this.viewport.height / 2) / TILE_PX),
    };
  }

  bubbleAnchor(entityId: string): ScreenPoint | undefined {
    const position = this.positionOf(entityId);
    const feet = position && this.feetOnScreen(position);
    return feet && { x: feet.x, y: feet.y - SPRITE_HEIGHT_PX };
  }
}

export const trackedWorld = new TrackedWorld();
server.on('snapshot', ({ entities }) => trackedWorld.reset(entities));
server.on('entity_moved', ({ entity_id, position }) => trackedWorld.move(entity_id, position));

let registered: WorldView | undefined;

export function setWorldView(view: WorldView): () => void {
  registered = view;
  return () => {
    if (registered === view) registered = undefined;
  };
}

export function worldView(): WorldView {
  return registered ?? trackedWorld;
}

export function distanceFromPlayer(view: WorldView, entityId: string): number | undefined {
  const player = view.positionOf(PLAYER_ID);
  const other = view.positionOf(entityId);
  if (!player || !other) return undefined;
  return Math.hypot(other.x - player.x, other.y - player.y);
}
