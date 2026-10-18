import { server, type Entity, type Position } from '../net';
import { mapOf } from '../world/map';

export const PLAYER_ID = 'player';

export type ScreenPoint = { x: number; y: number };
export type ScreenBox = { x: number; y: number; width: number; height: number };
export type ScreenSprite = { box: ScreenBox; depth: number; opaqueAt?(point: ScreenPoint): boolean };

/** What the dialogue UI needs from the world scene. README.md describes it. */
export interface WorldView {
  positionOf(entityId: string): Position | undefined;
  npcIds(): Iterable<string>;
  bubbleAnchor(entityId: string): ScreenPoint | undefined;
  spriteOf(entityId: string): ScreenSprite | undefined;
}

export const TILE_PX = 48;
const SPRITE_HEIGHT_PX = 72;

export class TrackedWorld implements WorldView {
  viewport = { width: 640, height: 360 };
  /** Game-canvas px per overlay px, so a tile is `TILE_PX` on the overlay. */
  scale = 1;
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

  /** Undefined for an NPC on another map than the player's. */
  positionOf(entityId: string): Position | undefined {
    const position = this.entities.get(entityId)?.position;
    return position && this.onPlayersMap(position) ? position : undefined;
  }

  *npcIds(): Iterable<string> {
    for (const { id, kind, position } of this.entities.values()) {
      if (kind === 'npc' && this.onPlayersMap(position)) yield id;
    }
  }

  private onPlayersMap(position: Position): boolean {
    const player = this.entities.get(PLAYER_ID)?.position;
    return !player || mapOf(position) === mapOf(player);
  }

  get tilePx(): number {
    return TILE_PX * this.scale;
  }

  feetOnScreen(position: Position): ScreenPoint | undefined {
    const player = this.positionOf(PLAYER_ID);
    if (!player) return undefined;
    return {
      x: this.viewport.width / 2 + (position.x - player.x) * this.tilePx,
      y: this.viewport.height / 2 + (position.y - player.y + 0.5) * this.tilePx,
    };
  }

  tileAt(point: ScreenPoint): Position | undefined {
    const player = this.positionOf(PLAYER_ID);
    if (!player) return undefined;
    return {
      x: Math.round(player.x + (point.x - this.viewport.width / 2) / this.tilePx),
      y: Math.round(player.y + (point.y - this.viewport.height / 2) / this.tilePx),
    };
  }

  bubbleAnchor(entityId: string): ScreenPoint | undefined {
    const position = this.positionOf(entityId);
    const feet = position && this.feetOnScreen(position);
    return feet && { x: feet.x, y: feet.y - SPRITE_HEIGHT_PX * this.scale };
  }

  spriteOf(entityId: string): ScreenSprite | undefined {
    const anchor = this.bubbleAnchor(entityId);
    if (!anchor) return undefined;
    const [width, height] = [this.tilePx, SPRITE_HEIGHT_PX * this.scale];
    return { box: { x: anchor.x - width / 2, y: anchor.y, width, height }, depth: anchor.y + height };
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
  if (!player || !other || mapOf(player) !== mapOf(other)) return undefined;
  return Math.hypot(other.x - player.x, other.y - player.y);
}
