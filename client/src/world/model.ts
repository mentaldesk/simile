import { server, type Entity, type Position } from '../net';
import { PLAYER_ID } from '../ui/world-view';
import { Mover } from './motion';
import { Player } from './player';

export type Npc = { id: string; name: string; mover: Mover };

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
      const npc = this.npcs.get(id);
      if (npc) npc.mover.moveTo(position);
      else this.npcs.set(id, { id, name, mover: new Mover(position) });
    }
    for (const id of this.npcs.keys()) if (!ids.has(id)) this.npcs.delete(id);
  }

  move(entityId: string, position: Position): void {
    this.npcs.get(entityId)?.mover.moveTo(position);
  }

  spawnPlayer(position: Position): Player {
    return (this.player ??= new Player(position));
  }

  update(dt: number): void {
    for (const { mover } of this.npcs.values()) mover.update(dt);
  }

  positionOf(entityId: string): Position | undefined {
    return entityId === PLAYER_ID ? this.player?.position : this.npcs.get(entityId)?.mover.position;
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
