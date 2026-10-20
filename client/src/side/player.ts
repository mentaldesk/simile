import type { Facing, Position } from '../net';
import { PLAYER_SPEED } from '../world/tuning';
import { isStanding, type ClimbKind, type Link, type SideMap, type Village } from './maps';
import { drawnCrossing, emptyDrawn, RIDE_SPEED, sideways, WALK_CYCLE_M, type Drawn } from './motion';
import { TILE_M } from './layout';
import { climbRuns, crossing, pointAlong, runAt, type Crossing, type Path, type Run } from './runs';

/** Tiles a second the player climbs: a little quicker than the residents. */
export const PLAYER_CLIMB: Record<ClimbKind, number> = { stairs: 2, ladder: 1.5 };

/** What's held this frame: x and y each -1, 0 or 1, y up the screen negative. `use` is E, pressed
 * this frame. */
export type Controls = { x: number; y: number; use: boolean };

export type MapPosition = Position & { map: string };

type OnRun = { run: Run; distance: number };
type Crossed = { crossing: Crossing; distance: number };

const sign = (value: number) => (value > 0 ? 1 : value < 0 ? -1 : 0);

/** The player in side view: left and right along the floor; E or up through a door; E onto stairs
 * or a ladder, then up and down along it, stopping anywhere; E for a lift's whole ride. */
export class SidePlayer {
  map: string;
  /** On `map`, in cells. */
  readonly position = { x: 0, y: 0 };
  /** Where it's drawn, in street cells. */
  readonly at = { x: 0, y: 0 };
  readonly drawn: Drawn = emptyDrawn();
  facing: Facing = 'east';
  walking = false;
  private heading = 1;
  private travelled = 0;
  private onRun?: OnRun;
  private crossed?: Crossed;
  /** A door only opens to up or down once they've been let go, so arriving doesn't go back. */
  private armed = true;
  private readonly village: Village;
  private readonly runs = new Map<string, Run[]>();
  private readonly reported: MapPosition = { x: 0, y: 0, map: '' };

  constructor(village: Village, position: MapPosition) {
    this.village = village;
    this.map = position.map;
    this.place(position);
    this.armed = true;
  }

  place({ x, y, map }: MapPosition): void {
    this.map = map;
    this.position.x = x;
    this.position.y = y;
    this.onRun = this.crossed = undefined;
    this.armed = false;
    this.locate();
  }

  /** Where the server and the dialogue UI have the player: the end of the stairs or lift they're
   * on until they arrive, as the protocol holds residents. The same object each time. */
  get mapPosition(): MapPosition {
    const end = this.crossed?.crossing.from;
    const reported = this.reported;
    reported.x = end?.x ?? this.position.x;
    reported.y = end?.y ?? this.position.y;
    reported.map = end?.map ?? this.map;
    return reported;
  }

  get climbing(): ClimbKind | 'lift' | undefined {
    return this.crossed?.crossing.kind ?? this.onRun?.run.kind;
  }

  /** The lift ride it's on, if any. */
  get riding(): Crossing | undefined {
    return this.crossed?.crossing.kind === 'lift' ? this.crossed.crossing : undefined;
  }

  /** The map it's drawn on: where a crossing started, until it arrives. */
  get drawnMap(): string {
    return this.crossed?.crossing.from.map ?? this.map;
  }

  /** Moves the player for a frame. Returns the door it's going through, for the scene to take it. */
  update(controls: Controls, dt: number): Link | undefined {
    if (controls.y === 0) this.armed = true;
    let door: Link | undefined;
    if (this.crossed) this.cross(this.crossed, controls, dt);
    else if (this.onRun) this.climb(this.onRun, controls, dt);
    else door = this.walk(controls, dt);
    this.locate();
    return door;
  }

  private walk(controls: Controls, dt: number): Link | undefined {
    const map = this.village.map(this.map);
    if (!map) return undefined;
    const x = Math.floor(this.position.x + 0.5);
    const y = Math.round(this.position.y);
    const link = controls.use || controls.y !== 0 ? this.village.linkAt(this.map, x, y) : undefined;
    const up = controls.y < 0 && this.armed;
    const down = controls.y > 0 && this.armed;
    if (link?.kind === 'door' && (controls.use || up || (down && link.side === 'inside' && map.kind === 'floor'))) {
      this.armed = false;
      return link;
    }
    if (controls.use) {
      const across = link && crossing(this.village, link);
      if (across) {
        this.crossed = { crossing: across, distance: 0 };
        return undefined;
      }
      const found = runAt(this.runsOf(map), { x, y });
      if (found) {
        this.onRun = found;
        return undefined;
      }
    }
    this.walking = false;
    if (controls.x !== 0) {
      this.heading = controls.x;
      this.facing = sideways(controls.x);
      const low = spanEnd(map, x, y, -1);
      const high = spanEnd(map, x, y, 1);
      const to = Math.min(Math.max(this.position.x + controls.x * PLAYER_SPEED * dt, low), high);
      this.walking = to !== this.position.x;
      this.travelled += Math.abs(to - this.position.x);
      this.position.x = to;
    } else if (controls.y !== 0) {
      this.facing = controls.y < 0 ? 'north' : 'south';
    }
    return undefined;
  }

  private climb(on: OnRun, controls: Controls, dt: number): void {
    const { path, kind } = on.run;
    const along = controls.y !== 0 ? -controls.y : kind === 'stairs' ? sign(controls.x * rise(path)) : 0;
    const outward = (on.distance <= 0 && along <= 0) || (on.distance >= path.total && along >= 0);
    if (controls.x !== 0 && controls.y === 0 && outward && this.endStanding(path, on.distance)) {
      this.onRun = undefined;
      this.walk(controls, dt);
      return;
    }
    this.move(on, path, along * PLAYER_CLIMB[kind] * dt);
    pointAlong(path, on.distance, this.position);
    if (along !== 0 && (on.distance <= 0 || on.distance >= path.total) && this.endStanding(path, on.distance)) {
      this.onRun = undefined;
      this.position.y = Math.round(this.position.y);
    }
  }

  private cross(crossed: Crossed, controls: Controls, dt: number): void {
    const { crossing: across } = crossed;
    const { path, kind, rising } = across;
    let along = 1;
    if (kind !== 'lift') {
      const towards = rising ? 1 : -1;
      const byX = kind === 'stairs' ? sign(controls.x * rise(path)) : 0;
      along = (controls.y !== 0 ? -controls.y : byX) * towards;
    }
    const speed = kind === 'lift' ? RIDE_SPEED : PLAYER_CLIMB[kind];
    this.move(crossed, path, along * speed * dt);
    if (crossed.distance >= path.total) {
      this.place({ x: across.to.x, y: across.to.y, map: across.to.map });
    } else if (crossed.distance <= 0 && along < 0) {
      this.crossed = undefined;
    }
  }

  private move(on: { distance: number }, path: Path, by: number): void {
    const before = on.distance;
    on.distance = Math.min(Math.max(before + by, 0), path.total);
    this.travelled += Math.abs(on.distance - before);
    const dx = path.points.at(-1)!.x - path.points[0].x;
    if (on.distance !== before && dx !== 0) this.heading = Math.sign(dx) * Math.sign(on.distance - before);
  }

  private endStanding(path: Path, distance: number): boolean {
    const end = distance <= 0 ? path.points[0] : path.points.at(-1)!;
    const map = this.village.map(this.map);
    return !!map && isStanding(map, end.x, end.y);
  }

  private runsOf(map: SideMap): Run[] {
    let runs = this.runs.get(map.id);
    if (!runs) this.runs.set(map.id, (runs = climbRuns(map)));
    return runs;
  }

  /** Where it's drawn, and how. */
  private locate(): void {
    const { drawn } = this;
    if (this.crossed) {
      const { crossing: across, distance } = this.crossed;
      pointAlong(across.path, distance, this.at);
      drawnCrossing(drawn, across.kind, this.heading, this.travelled);
      this.facing = drawn.facing;
      return;
    }
    const map = this.village.map(this.map);
    this.at.x = this.position.x + (map?.offset.x ?? 0);
    this.at.y = this.position.y + (map?.offset.y ?? 0);
    drawn.seated = false;
    if (this.onRun) {
      const { kind } = this.onRun.run;
      drawnCrossing(drawn, kind, this.heading, this.travelled);
      this.facing = drawn.facing;
      return;
    }
    drawn.on = undefined;
    drawn.facing = this.facing;
    drawn.pose = this.walking ? 'walking' : 'standing';
    drawn.phase = this.walking ? (this.travelled * TILE_M) / WALK_CYCLE_M : 0;
  }
}

/** Which way x goes as the path rises: 1 east, -1 west, 0 straight up. */
function rise(path: Path): number {
  const [first, last] = [path.points[0], path.points.at(-1)!];
  return sign((last.x - first.x) * sign(first.y - last.y));
}

/** The last cell to stand on from `x` along row `y`, going `way` (-1 west, 1 east). Stairs and
 * ladders are taken with E, so walking stops at them. */
export function spanEnd(map: SideMap, x: number, y: number, way: -1 | 1): number {
  let end = x;
  while (isStanding(map, end + way, y)) end += way;
  return end;
}
