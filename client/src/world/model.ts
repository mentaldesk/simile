import { server, type Entity, type Position } from '../net';
import { PLAYER_ID } from '../ui/world-view';
import { mapOf, VILLAGE, type MapPosition } from './map';
import { Mover } from './motion';
import { Player } from './player';

export type Npc = { id: string; name: string; map: string; mover: Mover };

/** The client owns the player: only the first snapshot places it, so reconnecting doesn't. */
export class WorldModel {
  player?: Player;
  readonly npcs = new Map<string, Npc>();
  private placedByServer = false;

  reset(entities: readonly Entity[]): void {
    const ids = new Set<string>();
    for (const { id, kind, name, position } of entities) {
      if (kind === 'player') {
        this.placePlayer(position);
        continue;
      }
      ids.add(id);
      if (this.npcs.has(id)) this.move(id, position);
      else this.npcs.set(id, { id, name, map: mapOf(position), mover: new Mover(position) });
    }
    for (const id of this.npcs.keys()) if (!ids.has(id)) this.npcs.delete(id);
  }

  move(entityId: string, position: Position): void {
    const npc = this.npcs.get(entityId);
    if (!npc) return;
    if (mapOf(position) === npc.map) return npc.mover.moveTo(position);
    npc.map = mapOf(position);
    npc.mover.place(position);
  }

  /** The map the player is on, the only one drawn. */
  get map(): string {
    return this.player?.map ?? VILLAGE;
  }

  /** The NPCs on the player's map, the only ones drawn, heard or picked. */
  *here(): Iterable<Npc> {
    for (const npc of this.npcs.values()) if (npc.map === this.map) yield npc;
  }

  spawnPlayer(position: Position): Player {
    return (this.player ??= new Player(position));
  }

  update(dt: number): void {
    for (const { mover } of this.npcs.values()) mover.update(dt);
  }

  /** Undefined for an NPC on another map. */
  positionOf(entityId: string): MapPosition | undefined {
    const position = this.whereIs(entityId);
    return position?.map === this.map ? position : undefined;
  }

  /** Wherever the entity is, on whichever map. */
  whereIs(entityId: string): MapPosition | undefined {
    if (entityId === PLAYER_ID) return this.player?.position;
    const npc = this.npcs.get(entityId);
    return npc && { ...npc.mover.position, map: npc.map };
  }

  private placePlayer(position: Position): void {
    if (this.placedByServer) return;
    this.placedByServer = true;
    if (this.player) this.player.place(position);
    else this.player = new Player(position);
  }
}

export const world = new WorldModel();
server.on('snapshot', ({ entities }) => world.reset(entities));
server.on('entity_moved', ({ entity_id, position }) => world.move(entity_id, position));
