import type { Facing, Position } from '../net';
import { PLAYER_SPEED } from '../world/tuning';
import { isStanding, type ClimbKind, type Link, type SideMap, type Village } from './maps';
import {
  BUFFER_SECONDS,
  COYOTE_SECONDS,
  dropBeyond,
  fly,
  footing,
  landingRow,
  JUMP_CUT,
  JUMP_SPEED,
  LANDING_SECONDS,
  steer,
  type Air,
} from './jump';
import { drawnCrossing, emptyDrawn, RIDE_SPEED, RUN_CYCLE_M, sideways, WALK_CYCLE_M, type Drawn } from './motion';
import { TILE_M } from './layout';
import { climbRuns, pointAlong, type Crossing, type Path, type Run } from './runs';
import { chosen, waysNear, type Press, type Way } from './ways';

/** Tiles a second. */
export const PLAYER_CLIMB: Record<ClimbKind, number> = { stairs: 2, ladder: 1.5 };
/** Times walking speed, running, along streets and floors and through the air. */
export const RUN_PACE = 2;
/** From a walk to a run, or back. */
export const RUN_BLEND_SECONDS = 0.25;

/** y negative up; `use` is E pressed since the last frame, `eTaken` E used by something in reach, `run` running
 * (Shift toggles it), `jump` Space pressed since the last frame and `hold` Space held. */
export type Controls = { x: number; y: number; use: boolean; eTaken: boolean; run: boolean; jump?: boolean; hold?: boolean };

export type MapPosition = Position & { map: string };

type OnRun = { run: Run; distance: number };
type Crossed = { crossing: Crossing; distance: number };
type Climb = Exclude<Way, { kind: 'door' }>;

const sign = (value: number) => (value > 0 ? 1 : value < 0 ? -1 : 0);
const EPSILON = 1e-6;

export class SidePlayer {
  map: string;
  /** On `map`, in cells. */
  readonly position = { x: 0, y: 0 };
  /** In street cells. */
  readonly at = { x: 0, y: 0 };
  /** In street cells: where the camera keeps to, `at` but for a jump's rise above where it left the ground. */
  readonly steady = { x: 0, y: 0 };
  /** In street cells, the row of whatever is under the feet. */
  ground = 0;
  readonly drawn: Drawn = emptyDrawn();
  facing: Facing = 'east';
  walking = false;
  private heading = 1;
  private travelled = 0;
  private strides = 0;
  /** 0 walking to 1 running. */
  private run = 0;
  private onRun?: OnRun;
  private crossed?: Crossed;
  /** Stepping to the end of what it's about to climb or ride. */
  private approaching?: Climb;
  /** Up or down only opens a door once let go, so arriving doesn't go back. */
  private armed = true;
  private air?: Air;
  /** Seconds left in which Space still jumps after walking off a ledge. */
  private coyote = 0;
  /** Seconds left in which a press of Space still jumps, on landing. */
  private buffered = 0;
  private landing = 0;
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
    this.onRun = this.crossed = this.approaching = this.air = undefined;
    this.coyote = this.buffered = this.landing = 0;
    this.armed = false;
    this.locate();
  }

  /** Held at the end left from while crossing, as the protocol holds residents. Reused: copy it to keep it. */
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

  get riding(): Crossing | undefined {
    return this.crossed?.crossing.kind === 'lift' ? this.crossed.crossing : undefined;
  }

  get drawnMap(): string {
    return this.crossed?.crossing.from.map ?? this.map;
  }

  /** Jumping or falling. */
  get airborne(): boolean {
    return !!this.air;
  }

  /** Returns the door to take, for the scene. */
  update(controls: Controls, dt: number): Link | undefined {
    if (controls.y === 0) this.armed = true;
    const blend = dt / RUN_BLEND_SECONDS;
    this.run = controls.run ? Math.min(this.run + blend, 1) : Math.max(this.run - blend, 0);
    this.buffered = controls.jump ? BUFFER_SECONDS : Math.max(this.buffered - dt, 0);
    this.landing = Math.max(this.landing - dt, 0);
    if (this.approaching && this.buffered > 0) this.approaching = undefined;
    let door: Link | undefined;
    if (this.crossed) this.cross(this.crossed, controls, dt);
    else if (this.onRun) this.climb(this.onRun, controls, dt);
    else if (this.approaching) this.approach(this.approaching, controls, dt);
    else if (this.air) this.fly(controls, dt);
    else door = this.walk(controls, dt);
    this.locate();
    return door;
  }

  /** What the player can take from here, nearest first: none while climbing or riding. */
  ways(): Way[] {
    const map = this.village.map(this.map);
    if (!map || this.onRun || this.crossed || this.approaching || this.air) return [];
    return waysNear(this.village, map, this.runsOf(map), this.position);
  }

  /** Tiles a second along a street or a floor. */
  get speed(): number {
    return PLAYER_SPEED * (1 + (RUN_PACE - 1) * this.run);
  }

  /** E takes a door; up or down, once let go since arriving, the lift or the nearest flight or ladder that way; Space
   * jumps. Walking stops at walls, stairs and ladders, and walks off a ledge. */
  private walk(controls: Controls, dt: number): Link | undefined {
    const map = this.village.map(this.map);
    if (!map) return undefined;
    const ways = this.ways();
    const vertical: Press | undefined = this.armed && controls.y !== 0 ? (controls.y < 0 ? 'up' : 'down') : undefined;
    const way = (controls.use ? chosen(ways, 'use') : undefined) ?? (vertical && chosen(ways, vertical, controls.eTaken));
    if (way?.kind === 'door') {
      this.armed = false;
      return way.link;
    }
    if (way) {
      if (Math.abs(way.at.x - this.position.x) <= EPSILON) this.begin(way);
      else this.approach((this.approaching = way), controls, dt);
      return undefined;
    }
    this.walking = false;
    const y = Math.round(this.position.y);
    if (controls.x !== 0) {
      const x = footing(map, this.position.x, y) ?? Math.floor(this.position.x + 0.5);
      this.heading = controls.x;
      this.facing = sideways(controls.x);
      const low = spanEnd(map, x, y, -1);
      const high = spanEnd(map, x, y, 1);
      const min = Math.min(dropBeyond(map, low, y, -1) ? 0 : low, this.position.x);
      const max = Math.max(dropBeyond(map, high, y, 1) ? map.width - 1 : high, this.position.x);
      const to = Math.min(Math.max(this.position.x + controls.x * this.speed * dt, min), max);
      this.walking = to !== this.position.x;
      this.stride(Math.abs(to - this.position.x));
      this.position.x = to;
    } else if (controls.y !== 0) {
      this.facing = controls.y < 0 ? 'north' : 'south';
    }
    if (this.buffered > 0) this.jump(controls.x);
    else if (footing(map, this.position.x, y) === undefined) {
      this.air = { vx: controls.x * this.speed, vy: 0, held: false };
      this.coyote = COYOTE_SECONDS;
      this.walking = false;
    }
    return undefined;
  }

  private jump(along: number): void {
    this.air = { vx: along * this.speed, vy: -JUMP_SPEED, held: true };
    this.buffered = this.coyote = this.landing = 0;
    this.walking = false;
  }

  /** Steered by the arrows, higher while Space is held, and landing on whatever is under it. */
  private fly(controls: Controls, dt: number): void {
    const map = this.village.map(this.map);
    if (!map) return;
    if (this.buffered > 0 && this.coyote > 0) this.jump(controls.x);
    this.coyote = Math.max(this.coyote - dt, 0);
    const flying = this.air!;
    if (flying.held && !controls.hold) {
      flying.held = false;
      if (flying.vy < 0) flying.vy *= JUMP_CUT;
    }
    if (controls.x !== 0) {
      this.heading = controls.x;
      this.facing = sideways(controls.x);
    }
    steer(flying, controls.x * this.speed, dt / 2);
    const from = this.position.x;
    const landed = fly(map, this.position, flying, dt);
    steer(flying, controls.x * this.speed, dt / 2);
    this.travelled += Math.abs(this.position.x - from);
    if (!landed) return;
    this.air = undefined;
    this.landing = LANDING_SECONDS;
    if (this.buffered > 0) this.jump(controls.x);
  }

  private begin(way: Climb): void {
    this.position.x = way.at.x;
    if ('across' in way) this.crossed = { crossing: way.across, distance: 0 };
    else this.onRun = { run: way.run, distance: way.distance };
  }

  /** Walks onto its end, then gets on; turning back lets it go. */
  private approach(way: Climb, controls: Controls, dt: number): void {
    const gap = way.at.x - this.position.x;
    if (controls.x !== 0 && Math.sign(controls.x) !== Math.sign(gap)) {
      this.approaching = undefined;
      this.armed = false;
      this.walk({ ...controls, y: 0, use: false }, dt);
      return;
    }
    const step = Math.min(Math.abs(gap), this.speed * dt);
    this.position.x += Math.sign(gap) * step;
    this.stride(step);
    this.heading = Math.sign(gap);
    this.facing = sideways(this.heading);
    this.walking = true;
    if (Math.abs(way.at.x - this.position.x) <= EPSILON) {
      this.approaching = undefined;
      this.walking = false;
      this.begin(way);
    }
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

  private stride(tiles: number): void {
    this.travelled += tiles;
    this.strides += (tiles * TILE_M) / (WALK_CYCLE_M + (RUN_CYCLE_M - WALK_CYCLE_M) * this.run);
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

  private locate(): void {
    const { drawn } = this;
    drawn.run = 0;
    if (this.crossed) {
      const { crossing: across, distance } = this.crossed;
      pointAlong(across.path, distance, this.at);
      this.steady.x = this.at.x;
      this.steady.y = this.ground = this.at.y;
      drawnCrossing(drawn, across.kind, this.heading, this.travelled);
      this.facing = drawn.facing;
      return;
    }
    const map = this.village.map(this.map);
    this.at.x = this.position.x + (map?.offset.x ?? 0);
    this.at.y = this.position.y + (map?.offset.y ?? 0);
    this.steady.x = this.at.x;
    this.steady.y = this.air ? Math.max(this.at.y, this.steady.y) : this.at.y;
    this.ground = this.air && map ? landingRow(map, this.position) + map.offset.y : this.at.y;
    drawn.seated = false;
    if (this.onRun) {
      const { kind } = this.onRun.run;
      drawnCrossing(drawn, kind, this.heading, this.travelled);
      this.facing = drawn.facing;
      return;
    }
    drawn.on = undefined;
    drawn.facing = this.facing;
    if (this.air) {
      drawn.pose = 'jumping';
      drawn.phase = this.air.vy < 0 ? 0 : 0.5;
      return;
    }
    const landing = !this.walking && this.landing > 0;
    drawn.pose = this.walking ? 'walking' : landing ? 'landing' : 'standing';
    drawn.phase = this.walking ? this.strides : landing ? 1 - this.landing / LANDING_SECONDS : 0;
    drawn.run = this.walking ? this.run : 0;
  }
}

/** 1 east, -1 west, 0 straight up. */
function rise(path: Path): number {
  const [first, last] = [path.points[0], path.points.at(-1)!];
  return sign((last.x - first.x) * sign(first.y - last.y));
}

/** Walking stops at stairs and ladders on a map, which are taken with up or down. */
export function spanEnd(map: SideMap, x: number, y: number, way: -1 | 1): number {
  let end = x;
  while (isStanding(map, end + way, y)) end += way;
  return end;
}
