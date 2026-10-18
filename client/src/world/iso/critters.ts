import { LOCATIONS_LAYER, objectsOf, type TiledMap } from '../map';
import type { Point } from '../view';
import {
  DUCK_POSES,
  duckFrame,
  HERON_POSES,
  heronFrame,
  PLUMAGES,
  rippleFrame,
  type CritterKind,
  type DuckPose,
  type HeronPose,
  type Plumage,
  type Ripple,
  type Side,
} from './critter-art';
import { groundHeights, type TiledMapWithTiles } from './ground';
import { DEFAULT_HOUR, LIGHTING_SETS } from './time-of-day';

type Span = readonly [number, number];

/** Counts, real seconds, tiles and sim hours for the critters on the water. */
export type CritterTuning = {
  cap: number;
  ducks: { lake: number; river: number };
  heron: boolean;
  rings: number;
  paddleSpeed: Span;
  apart: number;
  riseEvery: { day: Span; night: Span };
  settle: Span;
  wake: Span;
  heronHours: Span;
  heronAway: Span;
  heronStays: Span;
};

export const CRITTERS: CritterTuning = {
  cap: 12,
  ducks: { lake: 4, river: 2 },
  heron: true,
  rings: 4,
  paddleSpeed: [0.12, 0.24],
  apart: 1.2,
  riseEvery: { day: [2, 6], night: [9, 24] },
  settle: [20.5, 21.5],
  wake: [5, 6],
  heronHours: [6.5, 19.5],
  heronAway: [40, 200],
  heronStays: [60, 240],
};

/** Clear of the shores, in tiles: further from the near ones, whose kerbs hide the water by them. */
const FAR_SHORE = 0.45;
const NEAR_SHORE = 0.55;
const PERCH_OUT = 0.35;
const LOOK_AHEAD = 0.7;
const TURN_RATE = 1.6;
const WANDER_RATE = 0.5;
const WANDER_EVERY: Span = [1.5, 4];
const SIDE_DEADBAND = 0.2;
const MIN_GAP = 0.8;
/** The heron stands taller, so ducks keep further from it. */
const HERON_GAP = 1.4;
const HERON_ROOM = 1.8;
const RING_SECONDS = 0.35;
const RING_ALPHAS = [1, 1, 0.8, 0.5];
const FLIGHT_SECONDS = 5;
const FLIGHT_METRES = 5;
const FLIGHT_TILES = 6;
const WING_SECONDS = 0.22;
const TRIES = 12;
const TURNS = 6;
const TURN_COS = Float64Array.from({ length: 2 * TURNS + 1 }, (_, i) => Math.cos(((i - TURNS) * Math.PI) / TURNS));
const TURN_SIN = Float64Array.from({ length: 2 * TURNS + 1 }, (_, i) => Math.sin(((i - TURNS) * Math.PI) / TURNS));

const between = (span: Span, random: () => number) => span[0] + (span[1] - span[0]) * random();

/** A point of its own class: a plain `{ x, y }` shares its shape with every other, which can box its numbers. */
class Place implements Point {
  x = 0;
  y = 0;
}

const near = (dx: number, dy: number, apart: number) => dx * dx + dy * dy < apart * apart;

export type WaterKind = 'lake' | 'river';

export type WaterBody = { kind: WaterKind; tiles: number[]; perches: number[] };

/** Points are on the ground plane, in tiles. */
export class Water {
  readonly width: number;
  readonly height: number;
  readonly bodies: WaterBody[] = [];
  private readonly wet: Uint8Array;
  private readonly scratch = new Place();

  constructor(width: number, height: number, wet: Uint8Array, areas: readonly Area[] = []) {
    this.width = width;
    this.height = height;
    this.wet = wet;
    const seen = new Uint8Array(wet.length);
    for (let start = 0; start < wet.length; start++) {
      if (!wet[start] || seen[start]) continue;
      const tiles = this.fill(start, seen);
      const kind = tiles.some((i) => areas.some((area) => inArea(area, i % width, Math.floor(i / width))))
        ? 'lake'
        : 'river';
      this.bodies.push({ kind, tiles, perches: kind === 'lake' ? this.perchesOf(tiles) : [] });
    }
  }

  static of(map: TiledMap): Water {
    const water = groundHeights(map as TiledMapWithTiles, { water: 1 });
    const wet = new Uint8Array(map.width * map.height);
    for (let y = 0; y < map.height; y++) {
      for (let x = 0; x < map.width; x++) wet[y * map.width + x] = water({ x, y }) === 1 ? 1 : 0;
    }
    const size = map.tilewidth;
    const areas = objectsOf(map, LOCATIONS_LAYER).map(({ x = 0, y = 0, width = 0, height = 0 }) => ({
      x: x / size,
      y: y / size,
      width: width / size,
      height: height / size,
    }));
    return new Water(map.width, map.height, wet, areas);
  }

  isWater(x: number, y: number): boolean {
    return this.wetTile(Math.floor(x), Math.floor(y));
  }

  roomy(x: number, y: number, far = FAR_SHORE): boolean {
    this.scratch.x = x;
    this.scratch.y = y;
    return this.roomyAt(this.scratch, far);
  }

  roomyAt(point: Point, far = FAR_SHORE): boolean {
    const left = point.x - far;
    const right = point.x + NEAR_SHORE;
    const top = point.y - far;
    const bottom = point.y + NEAR_SHORE;
    const west = (left | 0) > left ? (left | 0) - 1 : left | 0;
    const east = (right | 0) > right ? (right | 0) - 1 : right | 0;
    const north = (top | 0) > top ? (top | 0) - 1 : top | 0;
    const south = (bottom | 0) > bottom ? (bottom | 0) - 1 : bottom | 0;
    return (
      this.wetTile(west, north) && this.wetTile(east, north) && this.wetTile(west, south) && this.wetTile(east, south)
    );
  }

  private wetTile(column: number, row: number): boolean {
    return (
      column >= 0 && row >= 0 && column < this.width && row < this.height && this.wet[row * this.width + column] === 1
    );
  }

  private fill(start: number, seen: Uint8Array): number[] {
    const tiles = [start];
    seen[start] = 1;
    for (let next = 0; next < tiles.length; next++) {
      const [x, y] = [tiles[next] % this.width, Math.floor(tiles[next] / this.width)];
      for (const [nx, ny] of [
        [x + 1, y],
        [x - 1, y],
        [x, y + 1],
        [x, y - 1],
      ]) {
        const i = ny * this.width + nx;
        if (!this.isWater(nx, ny) || seen[i]) continue;
        seen[i] = 1;
        tiles.push(i);
      }
    }
    return tiles;
  }

  /** Off the north and west shores, so the camera sees the heron in front of the kerb. */
  private perchesOf(tiles: readonly number[]): number[] {
    const perches: number[] = [];
    for (const i of tiles) {
      const [x, y] = [i % this.width, Math.floor(i / this.width)];
      if (!this.isWater(x + 0.5, y - 0.5) && this.roomy(x + 0.5, y + PERCH_OUT, PERCH_OUT)) {
        perches.push(x + 0.5, y + PERCH_OUT);
      }
      if (!this.isWater(x - 0.5, y + 0.5) && this.roomy(x + PERCH_OUT, y + 0.5, PERCH_OUT)) {
        perches.push(x + PERCH_OUT, y + 0.5);
      }
    }
    return perches;
  }
}

type Area = { x: number; y: number; width: number; height: number };

const inArea = (area: Area, x: number, y: number) =>
  x + 0.5 >= area.x && x + 0.5 <= area.x + area.width && y + 0.5 >= area.y && y + 0.5 <= area.y + area.height;

/** `z` is metres above the water. */
export type Critter = {
  readonly kind: CritterKind;
  x: number;
  y: number;
  z: number;
  frame: string;
  visible: boolean;
  alpha: number;
};

type DuckState = 'paddle' | 'rest' | 'dabble' | 'under' | 'preen' | 'tucked';

type Facing<T extends string> = Record<T, string>;
type Facings<T extends string> = Record<Side, Facing<T>>;

const facings = <T extends string>(poses: readonly T[], name: (pose: T, side: Side) => string): Facings<T> => {
  const side = (side: Side) => Object.fromEntries(poses.map((pose) => [pose, name(pose, side)])) as Facing<T>;
  return { left: side('left'), right: side('right') };
};

const DUCK_FRAMES = Object.fromEntries(
  PLUMAGES.map((plumage) => [plumage, facings(DUCK_POSES, (pose, side) => duckFrame(plumage, pose, side))]),
) as Record<Plumage, Facings<DuckPose>>;
const HERON_FRAMES = facings(HERON_POSES, heronFrame);
const RING_STEPS: Record<'koi' | 'fish', readonly string[]> = {
  koi: ['koi', 'ring1', 'ring2', 'ring3'].map((ripple) => rippleFrame(ripple as Ripple)),
  fish: ['fish', 'ring1', 'ring2', 'ring3'].map((ripple) => rippleFrame(ripple as Ripple)),
};

const DUCK_STATES: Record<DuckState, { frames: [DuckPose, DuckPose]; bob: number; pace: number; seconds: Span }> = {
  paddle: { frames: ['paddle0', 'paddle1'], bob: 0.55, pace: 1, seconds: [6, 20] },
  rest: { frames: ['paddle0', 'paddle1'], bob: 0.9, pace: 0, seconds: [3, 9] },
  preen: { frames: ['preen0', 'preen1'], bob: 0.45, pace: 0, seconds: [2, 5] },
  dabble: { frames: ['dabble', 'dabble'], bob: 1, pace: 0, seconds: [1.5, 3] },
  under: { frames: ['dabble', 'dabble'], bob: 1, pace: 1.5, seconds: [1.5, 3] },
  tucked: { frames: ['tucked', 'tucked'], bob: 1, pace: 0, seconds: [0, 0] },
};

const HERON_SECONDS: Record<HeronPose, Span> = {
  stand: [3, 9],
  hunch: [5, 15],
  strike: [0.4, 0.6],
  fly0: [0, 0],
  fly1: [0, 0],
};

class DuckCritter implements Critter {
  readonly kind = 'duck';
  x = 0;
  y = 0;
  z = 0;
  visible = true;
  alpha = 1;
  frame = '';
  frameA = '';
  frameB = '';
  state: DuckState = 'paddle';
  pace = 0;
  bob = 1;
  left = 0;
  clock = 0;
  turn = 0;
  turnIn = 0;
  /** A unit vector, not an angle, so steering needs no `Math.atan2`, which Maglev boxes. */
  hx = 1;
  hy = 0;
  side: Side;
  readonly facings: Facings<DuckPose>;
  readonly speed: number;
  readonly night: Span;

  constructor(x: number, y: number, plumage: Plumage, tuning: CritterTuning, random: () => number) {
    this.x = x;
    this.y = y;
    this.facings = DUCK_FRAMES[plumage];
    const heading = random() * 2 * Math.PI;
    this.hx = Math.cos(heading);
    this.hy = Math.sin(heading);
    this.side = random() < 0.5 ? 'left' : 'right';
    this.speed = between(tuning.paddleSpeed, random);
    this.night = [between(tuning.settle, random), between(tuning.wake, random)];
    this.clock = random() * 10;
  }
}

type HeronState = 'away' | 'arriving' | 'standing' | 'leaving';

class HeronCritter implements Critter {
  readonly kind = 'heron';
  x = 0;
  y = 0;
  z = 0;
  alpha = 1;
  visible = false;
  frame = HERON_FRAMES.left.stand;
  state: HeronState = 'away';
  pose: HeronPose = 'stand';
  left = 0;
  poseLeft = 0;
  clock = 0;
  side: Side = 'left';
  facing = HERON_FRAMES.left;
  readonly start = new Place();
  readonly end = new Place();
  rise = 0;
  fall = 0;
  readonly perch = new Place();
  readonly lake: WaterBody;

  constructor(lake: WaterBody, tuning: CritterTuning, random: () => number) {
    this.lake = lake;
    this.left = between(tuning.heronAway, random) / 2;
  }

  get flying(): boolean {
    return this.state === 'arriving' || this.state === 'leaving';
  }
}

class RingCritter implements Critter {
  readonly kind = 'ripple';
  x = 0;
  y = 0;
  z = 0;
  alpha = 1;
  visible = false;
  frame = RING_STEPS.fish[1];
  age = 0;
  steps = RING_STEPS.fish;
  /** The step to start on: 0 shows the fish rising, 1 starts at the first ring. */
  first = 0;
}

/** Each frame does the same work whatever a critter is doing, and boxes no numbers: optimised, it allocates nothing. */
export class Critters {
  readonly all: readonly Critter[];
  /** The sim hour, which `update` reads rather than takes, so it isn't boxed every frame. */
  hour: number = DEFAULT_HOUR;
  private readonly water: Water;
  private readonly tuning: CritterTuning;
  private readonly random: () => number;
  private readonly ducks: DuckCritter[] = [];
  private readonly heron?: HeronCritter;
  private readonly rings: RingCritter[] = [];
  private readonly risesIn: number[];
  private readonly spot = new Place();
  private readonly probe = new Place();

  constructor(water: Water, tuning: CritterTuning = CRITTERS, random: () => number = Math.random) {
    this.water = water;
    this.tuning = tuning;
    this.random = random;
    let room = Math.max(0, Math.floor(tuning.cap));
    for (const kind of ['lake', 'river'] as const) {
      for (const body of water.bodies.filter((body) => body.kind === kind)) {
        const count = Math.min(tuning.ducks[kind], room);
        for (let i = 0; i < count && this.findSpot(body); i++) {
          const plumage = PLUMAGES[this.ducks.length % PLUMAGES.length];
          const duck = new DuckCritter(this.spot.x, this.spot.y, plumage, tuning, random);
          this.ducks.push(duck);
          this.startDuck(duck, 'paddle');
        }
        room -= count;
      }
    }
    const lake = water.bodies.find(({ kind, perches }) => kind === 'lake' && perches.length > 0);
    if (tuning.heron && lake && room > 0) {
      this.heron = new HeronCritter(lake, tuning, random);
      room--;
    }
    for (let i = 0; i < Math.min(tuning.rings, room); i++) this.rings.push(new RingCritter());
    this.risesIn = water.bodies.map(() => between(tuning.riseEvery.day, random));
    this.all = [...this.ducks, ...(this.heron ? [this.heron] : []), ...this.rings];
  }

  update(dt: number): void {
    for (let i = 0; i < this.ducks.length; i++) this.updateDuck(this.ducks[i], dt);
    if (this.heron) this.updateHeron(this.heron, dt);
    for (let i = 0; i < this.rings.length; i++) this.updateRing(this.rings[i], dt);
    if (this.rings.length === 0) return;
    for (let i = 0; i < this.risesIn.length; i++) {
      if ((this.risesIn[i] -= dt) <= 0) this.rise(i);
    }
  }

  private within(span: Span): boolean {
    const { hour } = this;
    return span[0] < span[1] ? hour >= span[0] && hour < span[1] : hour >= span[0] || hour < span[1];
  }

  private updateDuck(duck: DuckCritter, dt: number): void {
    const tucked = duck.state === 'tucked';
    if (this.within(duck.night) !== tucked) this.startDuck(duck, tucked ? 'paddle' : 'tucked');
    duck.clock += dt;
    duck.left -= dt;
    if (duck.pace > 0) this.paddle(duck, dt);
    duck.frame = ((duck.clock / duck.bob) | 0) & 1 ? duck.frameB : duck.frameA;
    if (duck.left <= 0) this.nextDuck(duck);
  }

  private nextDuck(duck: DuckCritter): void {
    const { state } = duck;
    if (state === 'under') this.ring(duck.x, duck.y, 'fish', 1);
    const roll = this.random();
    if (state === 'dabble') this.startDuck(duck, roll < 0.5 ? 'under' : 'paddle');
    else if (state !== 'paddle') this.startDuck(duck, 'paddle');
    else this.startDuck(duck, roll < 0.3 ? 'rest' : roll < 0.5 ? 'dabble' : roll < 0.7 ? 'preen' : 'paddle');
  }

  private startDuck(duck: DuckCritter, state: DuckState): void {
    const { pace, bob, seconds } = DUCK_STATES[state];
    duck.state = state;
    duck.pace = pace;
    duck.bob = bob;
    duck.visible = state !== 'under';
    duck.left = state === 'tucked' ? Infinity : between(seconds, this.random);
    this.dress(duck);
  }

  private dress(duck: DuckCritter): void {
    const { frames } = DUCK_STATES[duck.state];
    const facing = duck.facings[duck.side];
    duck.frameA = facing[frames[0]];
    duck.frameB = facing[frames[1]];
    duck.frame = ((duck.clock / duck.bob) | 0) & 1 ? duck.frameB : duck.frameA;
  }

  private paddle(duck: DuckCritter, dt: number): void {
    const { probe } = this;
    if ((duck.turnIn -= dt) <= 0) {
      duck.turn = (this.random() * 2 - 1) * WANDER_RATE;
      duck.turnIn = WANDER_EVERY[0] + (WANDER_EVERY[1] - WANDER_EVERY[0]) * this.random();
    }
    let steer = duck.turn;
    if (this.ahead(duck, TURNS)) {
      let awayX = 0;
      let awayY = 0;
      for (let i = 0; i <= this.ducks.length; i++) {
        const other = this.presence(i);
        if (!other || other === duck) continue;
        const dx = duck.x - other.x;
        const dy = duck.y - other.y;
        const gap = Math.sqrt(dx * dx + dy * dy) + 1e-9;
        const reach = i < this.ducks.length ? this.tuning.apart : HERON_ROOM;
        const push = gap < reach ? (reach - gap) / gap : 0;
        awayX += dx * push;
        awayY += dy * push;
      }
      const cross = duck.hx * awayY - duck.hy * awayX;
      const dot = duck.hx * awayX + duck.hy * awayY;
      const onCourse = dot > 0 && cross < 0.1 * dot && cross > -0.1 * dot;
      if (awayX !== 0 || awayY !== 0) steer = onCourse ? 0 : cross > 0 ? TURN_RATE : -TURN_RATE;
    } else steer = TURN_RATE * this.shoreTurn(duck);
    const turn = steer * dt;
    const cos = 1 - (turn * turn) / 2;
    const sin = turn - (turn * turn * turn) / 6;
    const hx = duck.hx * cos - duck.hy * sin;
    const hy = duck.hx * sin + duck.hy * cos;
    const length = Math.sqrt(hx * hx + hy * hy);
    duck.hx = hx / length;
    duck.hy = hy / length;
    const step = duck.speed * duck.pace * dt;
    probe.x = duck.x + duck.hx * step;
    probe.y = duck.y + duck.hy * step;
    if (this.water.roomyAt(probe) && !this.crowds(duck)) {
      duck.x = probe.x;
      duck.y = probe.y;
    }
    const across = duck.hx - duck.hy;
    const side = across < -SIDE_DEADBAND ? 'left' : across > SIDE_DEADBAND ? 'right' : duck.side;
    if (side !== duck.side) this.turnDuck(duck, side);
  }

  /** 1 or -1, not a turn rate: a fractional return would keep the steering boxed in Maglev. */
  private shoreTurn(duck: DuckCritter): number {
    for (let k = 1; k <= TURNS; k++) {
      if (this.ahead(duck, TURNS + k)) return 1;
      if (this.ahead(duck, TURNS - k)) return -1;
    }
    return 1;
  }

  private turnDuck(duck: DuckCritter, side: Side): void {
    duck.side = side;
    this.dress(duck);
  }

  private ahead(duck: DuckCritter, turn: number): boolean {
    const cos = TURN_COS[turn];
    const sin = TURN_SIN[turn];
    this.probe.x = duck.x + (duck.hx * cos - duck.hy * sin) * LOOK_AHEAD;
    this.probe.y = duck.y + (duck.hx * sin + duck.hy * cos) * LOOK_AHEAD;
    return this.water.roomyAt(this.probe);
  }

  private presence(i: number): Point | undefined {
    if (i < this.ducks.length) return this.ducks[i];
    const heron = this.heron;
    return heron && (heron.state === 'arriving' || heron.state === 'standing') ? heron.perch : undefined;
  }

  private crowds(self: Critter): boolean {
    const { probe } = this;
    for (let i = 0; i <= this.ducks.length; i++) {
      const other = this.presence(i);
      if (!other || other === self) continue;
      const nx = probe.x - other.x;
      const ny = probe.y - other.y;
      const sx = self.x - other.x;
      const sy = self.y - other.y;
      const gap = Math.sqrt(nx * nx + ny * ny);
      const least = i < this.ducks.length ? MIN_GAP : HERON_GAP;
      if (gap < least && gap < Math.sqrt(sx * sx + sy * sy)) return true;
    }
    return false;
  }

  private rise(i: number): void {
    this.risesIn[i] = between(
      this.within(LIGHTING_SETS.night) ? this.tuning.riseEvery.night : this.tuning.riseEvery.day,
      this.random,
    );
    const body = this.water.bodies[i];
    if (!this.findSpot(body)) return;
    this.ring(this.spot.x, this.spot.y, body.kind === 'lake' && this.random() < 0.5 ? 'koi' : 'fish', 0);
  }

  private findSpot(body: WaterBody, apart = this.tuning.apart): boolean {
    for (let attempt = 0; attempt < TRIES; attempt++) {
      const tile = body.tiles[Math.floor(this.random() * body.tiles.length)];
      const x = (tile % this.water.width) + this.random();
      const y = Math.floor(tile / this.water.width) + this.random();
      if (this.water.roomy(x, y) && this.clear(x, y, apart)) {
        this.spot.x = x;
        this.spot.y = y;
        return true;
      }
    }
    return false;
  }

  private clear(x: number, y: number, apart: number): boolean {
    for (let i = 0; i <= this.ducks.length; i++) {
      const other = this.presence(i);
      if (other && near(x - other.x, y - other.y, apart)) return false;
    }
    for (let i = 0; i < this.rings.length; i++) {
      const ring = this.rings[i];
      if (ring.visible && near(x - ring.x, y - ring.y, apart)) return false;
    }
    return true;
  }

  private updateHeron(heron: HeronCritter, dt: number): void {
    heron.clock += dt;
    heron.left -= dt;
    heron.poseLeft -= dt;
    const flown = heron.clock / FLIGHT_SECONDS;
    const t = flown < 1 ? flown : 1;
    const easeIn = t * t;
    const easeOut = 1 - (1 - t) * (1 - t);
    const near = heron.state === 'leaving' ? easeIn : easeOut;
    const { start, end } = heron;
    heron.x = start.x + (end.x - start.x) * near;
    heron.y = start.y + (end.y - start.y) * near;
    heron.z = heron.rise + (heron.fall - heron.rise) * near;
    const wings = (((heron.clock / WING_SECONDS) | 0) & 1) === 0;
    const flying = heron.flying;
    if (flying) heron.frame = wings ? heron.facing.fly0 : heron.facing.fly1;
    const day = this.within(this.tuning.heronHours);
    if (flying ? t >= 1 : heron.left <= 0 || (!day && heron.state === 'standing')) this.nextHeron(heron, day);
    else if (heron.state === 'standing' && heron.poseLeft <= 0) this.nextHeronPose(heron);
  }

  private nextHeron(heron: HeronCritter, day: boolean): void {
    const { tuning, random } = this;
    switch (heron.state) {
      case 'arriving':
        heron.state = 'standing';
        this.hold(heron);
        heron.left = between(tuning.heronStays, random);
        this.poseHeron(heron, 'stand');
        break;
      case 'leaving':
        heron.state = 'away';
        heron.visible = false;
        heron.left = between(tuning.heronAway, random);
        break;
      case 'standing':
        this.fly(heron, 'leaving');
        break;
      case 'away':
        if (day) this.land(heron);
        else heron.left = between(tuning.heronAway, random) / 4;
        break;
    }
  }

  private land(heron: HeronCritter): void {
    const { perches } = heron.lake;
    const count = perches.length / 2;
    const first = Math.floor(this.random() * count);
    for (let k = 0; k < count; k++) {
      const i = ((first + k) % count) * 2;
      if (!this.clear(perches[i], perches[i + 1], HERON_ROOM)) continue;
      heron.perch.x = perches[i];
      heron.perch.y = perches[i + 1];
      const way = this.random() < 0.5 ? 1 : -1;
      heron.side = way > 0 ? 'left' : 'right';
      heron.facing = HERON_FRAMES[heron.side];
      this.fly(heron, 'arriving', way);
      return;
    }
    heron.left = between(this.tuning.heronAway, this.random) / 4;
  }

  private fly(heron: HeronCritter, state: 'arriving' | 'leaving', way = heron.side === 'left' ? 1 : -1): void {
    const arriving = state === 'arriving';
    const { perch } = heron;
    const away = arriving ? heron.start : heron.end;
    const onPerch = arriving ? heron.end : heron.start;
    away.x = perch.x + way * FLIGHT_TILES;
    away.y = perch.y - way * FLIGHT_TILES;
    onPerch.x = perch.x;
    onPerch.y = perch.y;
    heron.rise = arriving ? FLIGHT_METRES : 0;
    heron.fall = arriving ? 0 : FLIGHT_METRES;
    if (!arriving) {
      heron.side = way > 0 ? 'right' : 'left';
      heron.facing = HERON_FRAMES[heron.side];
    }
    heron.state = state;
    heron.visible = true;
    heron.clock = 0;
    heron.x = heron.start.x;
    heron.y = heron.start.y;
    heron.z = heron.rise;
    heron.frame = heron.facing.fly0;
  }

  private hold(heron: HeronCritter): void {
    heron.start.x = heron.end.x = heron.perch.x;
    heron.start.y = heron.end.y = heron.perch.y;
    heron.rise = 0;
    heron.fall = 0;
  }

  private nextHeronPose(heron: HeronCritter): void {
    if (heron.pose === 'strike') {
      const reach = heron.side === 'left' ? -0.3 : 0.3;
      if (this.water.roomy(heron.x + reach, heron.y - reach)) this.ring(heron.x + reach, heron.y - reach, 'fish', 1);
    }
    const roll = this.random();
    this.poseHeron(heron, heron.pose !== 'stand' ? 'stand' : roll < 0.4 ? 'hunch' : roll < 0.6 ? 'strike' : 'stand');
  }

  private poseHeron(heron: HeronCritter, pose: HeronPose): void {
    heron.pose = pose;
    heron.poseLeft = between(HERON_SECONDS[pose], this.random);
    heron.frame = heron.facing[pose];
  }

  private ring(x: number, y: number, rise: keyof typeof RING_STEPS, first: number): void {
    for (let i = 0; i < this.rings.length; i++) {
      const ring = this.rings[i];
      if (ring.visible) continue;
      ring.x = x;
      ring.y = y;
      ring.steps = RING_STEPS[rise];
      ring.first = first;
      ring.age = 0;
      ring.visible = true;
      this.updateRing(ring, 0);
      return;
    }
  }

  private updateRing(ring: RingCritter, dt: number): void {
    if (!ring.visible) return;
    ring.age += dt;
    const step = ring.first + ((ring.age / RING_SECONDS) | 0);
    if (step >= RING_ALPHAS.length) {
      ring.visible = false;
      return;
    }
    ring.frame = ring.steps[step];
    ring.alpha = RING_ALPHAS[step];
  }
}
