import { server, type Entity, type EntityMovedMessage, type Facing, type Pose, type Position } from '../net';
import { WALKING_SPEED } from '../world/tuning';
import { cellOf, type Village } from './maps';
import {
  CLIMB_SPEED,
  drawnCrossing,
  drawnOnMap,
  emptyDrawn,
  RIDE_SPEED,
  Walker,
  type Drawn,
} from './motion';
import { settle } from './poses';
import { crossing, pointAlong, type Crossing } from './runs';

type Under = { crossing: Crossing; distance: number; arrival?: Position & { map: string } };

export class Resident {
  readonly id: string;
  readonly name: string;
  map: string;
  pose: Pose;
  facing: Facing;
  readonly walker: Walker;
  /** Waiting to reach its end before crossing. */
  pending?: Crossing;
  under?: Under;
  idle = 0;
  /** How far into bed, 0 up to 1 lying. */
  bed: number;
  /** In street cells. */
  readonly at = { x: 0, y: 0 };
  readonly drawn: Drawn = emptyDrawn();

  constructor({ id, name, position, pose = 'standing', facing = 'south_east' }: Entity) {
    this.id = id;
    this.name = name;
    this.map = position.map ?? '';
    this.pose = pose;
    this.facing = facing;
    this.walker = new Walker(position, WALKING_SPEED);
    this.bed = pose === 'sleeping' ? 1 : 0;
  }

  get drawnMap(): string {
    return this.under?.crossing.from.map ?? this.map;
  }
}

export class Residents {
  readonly all = new Map<string, Resident>();
  village?: Village;
  start?: Position & { map: string };

  reset(entities: readonly Entity[], mapId?: string): void {
    const ids = new Set<string>();
    for (const entity of entities) {
      if (entity.kind === 'player') {
        const { x, y, map = mapId ?? '' } = entity.position;
        this.start = { x, y, map };
      }
      if (entity.kind !== 'npc') continue;
      ids.add(entity.id);
      const known = this.all.get(entity.id);
      if (!known) {
        this.all.set(entity.id, new Resident(entity));
        continue;
      }
      this.move({ type: 'entity_moved', entity_id: entity.id, ...entity });
      known.bed = entity.pose === 'sleeping' ? 1 : 0;
      if (!known.bed) continue;
      known.walker.place(entity.position);
      known.pending = known.under = undefined;
    }
    for (const id of this.all.keys()) if (!ids.has(id)) this.all.delete(id);
  }

  move({ entity_id, position, pose = 'standing', facing = 'south_east' }: EntityMovedMessage): void {
    const resident = this.all.get(entity_id);
    if (!resident) return;
    const map = position.map ?? resident.map;
    resident.pose = pose;
    resident.facing = facing;
    const { under, pending } = resident;
    const arrival = { x: position.x, y: position.y, map };
    if (under && map === under.crossing.to.map) {
      under.arrival = arrival;
      return;
    }
    if (pending && map === pending.to.map) {
      resident.walker.place(pending.from);
      resident.under = { crossing: pending, distance: 0, arrival };
      resident.pending = undefined;
      return;
    }
    const { x, y } = cellOf(position);
    if (under && x === under.crossing.from.x && y === under.crossing.from.y) return;
    if (map !== resident.map || under) {
      resident.map = map;
      resident.walker.place(position);
      resident.pending = resident.under = undefined;
      return;
    }
    resident.walker.moveTo(position);
    resident.pending = this.crossingFrom(map, position, pose);
  }

  update(dt: number): void {
    for (const resident of this.all.values()) this.step(resident, dt);
  }

  private crossingFrom(map: string, position: Position, pose: Pose): Crossing | undefined {
    if (pose !== 'climbing' && pose !== 'riding') return undefined;
    const { x, y } = cellOf(position);
    const link = this.village?.linkAt(map, x, y);
    const found = link && this.village && crossing(this.village, link);
    return found && (found.kind === 'lift') === (pose === 'riding') ? found : undefined;
  }

  private step(resident: Resident, dt: number): void {
    const { walker } = resident;
    const abed = resident.pose === 'sleeping' && walker.arrived && !resident.pending && !resident.under;
    if (resident.bed > 0 && !abed) resident.bed = settle(resident.bed, false, dt);
    else walker.update(dt);
    if (abed) resident.bed = settle(resident.bed, true, dt);
    resident.drawn.bed = resident.bed;
    resident.idle += dt;
    const { pending } = resident;
    if (pending && walker.arrived) {
      resident.under = { crossing: pending, distance: 0 };
      resident.pending = undefined;
    }
    const { under } = resident;
    if (under) {
      const { kind, path } = under.crossing;
      const speed = kind === 'lift' ? RIDE_SPEED : CLIMB_SPEED[kind];
      const before = under.distance;
      under.distance = Math.min(path.total, before + speed * dt);
      walker.travelled += under.distance - before;
      pointAlong(path, under.distance, resident.at);
      const dx = path.points.at(-1)!.x - path.points[0].x;
      if (dx !== 0) walker.heading = Math.sign(dx);
      drawnCrossing(resident.drawn, kind, walker.heading, walker.travelled);
      if (under.distance >= path.total && under.arrival) {
        resident.map = under.arrival.map;
        walker.place(under.arrival);
        resident.under = undefined;
      }
      return;
    }
    const map = this.village?.map(resident.map);
    resident.at.x = walker.position.x + (map?.offset.x ?? 0);
    resident.at.y = walker.position.y + (map?.offset.y ?? 0);
    drawnOnMap(resident.drawn, map, walker.position, resident, walker, resident.idle);
  }
}

export const sideResidents = new Residents();
server.on('snapshot', ({ entities, map_id }) => sideResidents.reset(entities, map_id));
server.on('entity_moved', (message) => sideResidents.move(message));
// So a tab that wasn't in the game when the player collapsed starts them at home.
server.on('player_collapsed', ({ position: { x, y, map = '' } }) => (sideResidents.start = { x, y, map }));
