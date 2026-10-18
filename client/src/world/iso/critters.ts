import { LOCATIONS_LAYER, objectsOf, type TiledMap } from '../map';
import {
  DUCK_POSES,
  duckFrame,
  HERON_POSES,
  heronFrame,
  PLUMAGES,
  rippleFrame,
  RIPPLES,
  type CritterKind,
  type DuckPose,
  type HeronPose,
  type Plumage,
  type Ripple,
  type Side,
} from './critter-art';
import { groundHeights, type TiledMapWithTiles } from './ground';
import { LIGHTING_SETS } from './time-of-day';

type Span = readonly [number, number];

/** Counts, real seconds, tiles and sim hours for the critters on the water. */
export type CritterTuning = {
  /** The most there are at once, rings on the water included. */
  cap: number;
  /** On each lake, which is water inside a location, and on each river, which is water outside one. */
  ducks: { lake: number; river: number };
  heron: boolean;
  /** Fish rising and ducks surfacing, at once. */
  rings: number;
  paddleSpeed: Span;
  apart: number;
  riseEvery: { day: Span; night: Span };
  /** Sim hours between which each duck tucks its head in, and wakes. */
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
/** The heron stands this far out from the north or west shore. */
const PERCH_OUT = 0.35;
const LOOK_AHEAD = 0.7;
const TURN_RATE = 1.6;
const WANDER_RATE = 0.5;
const WANDER_EVERY: Span = [1.5, 4];
const SIDE_DEADBAND = 0.2;
/** Nobody moves closer to anyone than this. */
const MIN_GAP = 0.8;
/** The heron stands taller, so ducks keep further from it. */
const HERON_GAP = 1.4;
const HERON_ROOM = 1.8;
const BOB_SECONDS = 0.55;
const PREEN_SECONDS = 0.45;
const RING_SECONDS = 0.35;
const RING_ALPHAS = [1, 1, 0.8, 0.5];
const FLIGHT_SECONDS = 5;
const FLIGHT_METRES = 5;
const FLIGHT_TILES = 6;
const WING_SECONDS = 0.22;
const TRIES = 12;

const between = (span: Span, random: () => number) => span[0] + (span[1] - span[0]) * random();

/** Not `Math.hypot`, which boxes its arguments on every call. */
const distance = (dx: number, dy: number) => Math.sqrt(dx * dx + dy * dy);

export const inHours = (hour: number, start: number, end: number): boolean =>
  start < end ? hour >= start && hour < end : hour >= start || hour < end;

const night = (hour: number) => inHours(hour, LIGHTING_SETS.night[0], LIGHTING_SETS.night[1]);

export type WaterKind = 'lake' | 'river';

/** `tiles` are indices into the map; `perches`, x and y pairs, where a heron can stand. */
export type WaterBody = { kind: WaterKind; tiles: number[]; perches: number[] };

/** The map's `water` ground tiles, in connected bodies. Points are on the ground plane, in tiles. */
export class Water {
  readonly width: number;
  readonly height: number;
  readonly bodies: WaterBody[] = [];
  private readonly wet: Uint8Array;

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
    const column = Math.floor(x);
    const row = Math.floor(y);
    return (
      column >= 0 && row >= 0 && column < this.width && row < this.height && this.wet[row * this.width + column] === 1
    );
  }

  /** Room for a critter: water all round it, and clear of the shores. */
  roomy(x: number, y: number, far = FAR_SHORE): boolean {
    return (
      this.isWater(x - far, y - far) &&
      this.isWater(x + NEAR_SHORE, y - far) &&
      this.isWater(x - far, y + NEAR_SHORE) &&
      this.isWater(x + NEAR_SHORE, y + NEAR_SHORE)
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

  /** In the water off the far shores, north and west, which the camera sees past the heron. */
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

/** What's drawn: `z` is metres above the water. */
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

type Sided<T extends string> = Record<T, Record<Side, string>>;

const sidedFrames = <T extends string>(poses: readonly T[], name: (pose: T, side: Side) => string): Sided<T> =>
  Object.fromEntries(poses.map((pose) => [pose, { left: name(pose, 'left'), right: name(pose, 'right') }])) as Sided<T>;

const DUCK_FRAMES = Object.fromEntries(
  PLUMAGES.map((plumage) => [plumage, sidedFrames(DUCK_POSES, (pose, side) => duckFrame(plumage, pose, side))]),
) as Record<Plumage, Sided<DuckPose>>;
const HERON_FRAMES = sidedFrames(HERON_POSES, heronFrame);
const RING_FRAMES = Object.fromEntries(RIPPLES.map((ripple) => [ripple, rippleFrame(ripple)])) as Record<
  Ripple,
  string
>;

class DuckCritter implements Critter {
  readonly kind = 'duck';
  x = 0;
  y = 0;
  z = 0;
  visible = true;
  alpha = 1;
  frame: string;
  state: DuckState = 'paddle';
  left = 0;
  clock = 0;
  turn = 0;
  turnIn = 0;
  side: Side;
  heading = 0;
  readonly frames: Sided<DuckPose>;
  readonly speed: number;
  readonly settle: number;
  readonly wake: number;

  constructor(x: number, y: number, plumage: Plumage, tuning: CritterTuning, random: () => number) {
    this.x = x;
    this.y = y;
    this.frames = DUCK_FRAMES[plumage];
    this.heading = random() * 2 * Math.PI;
    this.side = random() < 0.5 ? 'left' : 'right';
    this.frame = this.frames.paddle0[this.side];
    this.speed = between(tuning.paddleSpeed, random);
    this.settle = between(tuning.settle, random);
    this.wake = between(tuning.wake, random);
    this.left = between([2, 12], random);
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
  frame = HERON_FRAMES.stand.left;
  state: HeronState = 'away';
  pose: HeronPose = 'stand';
  left = 0;
  poseLeft = 0;
  clock = 0;
  side: Side = 'left';
  readonly from = { x: 0, y: 0 };
  readonly perch = { x: 0, y: 0 };
  readonly lake: WaterBody;

  constructor(lake: WaterBody, tuning: CritterTuning, random: () => number) {
    this.lake = lake;
    this.left = between(tuning.heronAway, random) / 2;
  }
}

class RingCritter implements Critter {
  readonly kind = 'ripple';
  x = 0;
  y = 0;
  z = 0;
  alpha = 1;
  visible = false;
  frame = RING_FRAMES.ring1;
  age = 0;
  rise: Ripple = 'fish';
  /** 0 to show the fish rising first, or 1 to start at the first ring. */
  first = 0;
}

export class Critters {
  readonly all: readonly Critter[];
  private readonly water: Water;
  private readonly tuning: CritterTuning;
  private readonly random: () => number;
  private readonly ducks: DuckCritter[] = [];
  private readonly heron?: HeronCritter;
  private readonly rings: RingCritter[] = [];
  private readonly risesIn: number[];
  private readonly spot = { x: 0, y: 0 };

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
          this.ducks.push(new DuckCritter(this.spot.x, this.spot.y, plumage, tuning, random));
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

  /** `dt` in real seconds, at a sim `hour`. */
  update(dt: number, hour: number): void {
    for (let i = 0; i < this.ducks.length; i++) this.updateDuck(this.ducks[i], dt, hour);
    if (this.heron) this.updateHeron(this.heron, dt, hour);
    for (let i = 0; i < this.rings.length; i++) this.updateRing(this.rings[i], dt);
    if (this.rings.length === 0) return;
    const rising = night(hour) ? this.tuning.riseEvery.night : this.tuning.riseEvery.day;
    for (let i = 0; i < this.risesIn.length; i++) {
      this.risesIn[i] -= dt;
      if (this.risesIn[i] > 0) continue;
      this.risesIn[i] = between(rising, this.random);
      const body = this.water.bodies[i];
      if (this.findSpot(body)) {
        const koi = body.kind === 'lake' && this.random() < 0.5;
        this.ring(this.spot.x, this.spot.y, koi ? 'koi' : 'fish', 0);
      }
    }
  }

  private updateDuck(duck: DuckCritter, dt: number, hour: number): void {
    if (inHours(hour, duck.settle, duck.wake)) {
      duck.state = 'tucked';
      duck.visible = true;
      duck.frame = duck.frames.tucked[duck.side];
      return;
    }
    if (duck.state === 'tucked') this.startDuck(duck, 'paddle');
    duck.clock += dt;
    duck.left -= dt;
    const { frames, side } = duck;
    switch (duck.state) {
      case 'paddle':
        this.paddle(duck, dt, 1);
        duck.frame = this.bob(duck, BOB_SECONDS) ? frames.paddle0[duck.side] : frames.paddle1[duck.side];
        if (duck.left <= 0) this.nextDuck(duck);
        break;
      case 'rest':
        duck.frame = this.bob(duck, BOB_SECONDS * 1.6) ? frames.paddle0[side] : frames.paddle1[side];
        if (duck.left <= 0) this.startDuck(duck, 'paddle');
        break;
      case 'preen':
        duck.frame = this.bob(duck, PREEN_SECONDS) ? frames.preen0[side] : frames.preen1[side];
        if (duck.left <= 0) this.startDuck(duck, 'paddle');
        break;
      case 'dabble':
        duck.frame = frames.dabble[side];
        if (duck.left <= 0) this.startDuck(duck, this.random() < 0.5 ? 'under' : 'paddle');
        break;
      case 'under':
        duck.visible = false;
        this.paddle(duck, dt, 1.5);
        if (duck.left <= 0) {
          duck.visible = true;
          this.ring(duck.x, duck.y, 'fish', 1);
          this.startDuck(duck, 'paddle');
        }
        break;
    }
  }

  private bob(duck: DuckCritter, seconds: number): boolean {
    return duck.clock % (2 * seconds) < seconds;
  }

  private nextDuck(duck: DuckCritter): void {
    const roll = this.random();
    this.startDuck(duck, roll < 0.3 ? 'rest' : roll < 0.5 ? 'dabble' : roll < 0.7 ? 'preen' : 'paddle');
  }

  private startDuck(duck: DuckCritter, state: DuckState): void {
    duck.state = state;
    duck.visible = true;
    duck.left = between(DUCK_SECONDS[state], this.random);
  }

  private paddle(duck: DuckCritter, dt: number, pace: number): void {
    const { random, water } = this;
    if ((duck.turnIn -= dt) <= 0) {
      duck.turn = (random() * 2 - 1) * WANDER_RATE;
      duck.turnIn = between(WANDER_EVERY, random);
    }
    let steer = duck.turn;
    if (!this.ahead(duck, duck.heading)) {
      steer = TURN_RATE;
      for (let k = 1; k <= 6; k++) {
        if (this.ahead(duck, duck.heading + (k * Math.PI) / 6)) break;
        if (this.ahead(duck, duck.heading - (k * Math.PI) / 6)) {
          steer = -TURN_RATE;
          break;
        }
      }
    } else {
      let awayX = 0;
      let awayY = 0;
      for (let i = 0; i <= this.ducks.length; i++) {
        const other = this.presence(i);
        if (!other || other === duck) continue;
        const dx = duck.x - other.x;
        const dy = duck.y - other.y;
        const gap = distance(dx, dy);
        const reach = i < this.ducks.length ? this.tuning.apart : HERON_ROOM;
        if (gap === 0 || gap >= reach) continue;
        awayX += (dx / gap) * (reach - gap);
        awayY += (dy / gap) * (reach - gap);
      }
      if (awayX !== 0 || awayY !== 0) {
        const off = wrap(Math.atan2(awayY, awayX) - duck.heading);
        steer = Math.abs(off) < 0.1 ? 0 : Math.sign(off) * TURN_RATE;
      }
    }
    duck.heading = wrap(duck.heading + steer * dt);
    const step = duck.speed * pace * dt;
    const x = duck.x + Math.cos(duck.heading) * step;
    const y = duck.y + Math.sin(duck.heading) * step;
    if (water.roomy(x, y) && !this.crowds(duck, x, y)) {
      duck.x = x;
      duck.y = y;
    }
    const across = Math.cos(duck.heading) - Math.sin(duck.heading);
    if (across < -SIDE_DEADBAND) duck.side = 'left';
    else if (across > SIDE_DEADBAND) duck.side = 'right';
  }

  private ahead(duck: DuckCritter, heading: number): boolean {
    return this.water.roomy(duck.x + Math.cos(heading) * LOOK_AHEAD, duck.y + Math.sin(heading) * LOOK_AHEAD);
  }

  /** Each duck, then the heron where it's landing or standing. */
  private presence(i: number): { x: number; y: number } | undefined {
    if (i < this.ducks.length) return this.ducks[i];
    const heron = this.heron;
    return heron && (heron.state === 'arriving' || heron.state === 'standing') ? heron.perch : undefined;
  }

  private crowds(self: Critter, x: number, y: number): boolean {
    for (let i = 0; i <= this.ducks.length; i++) {
      const other = this.presence(i);
      if (!other || other === self) continue;
      const gap = distance(x - other.x, y - other.y);
      const least = i < this.ducks.length ? MIN_GAP : HERON_GAP;
      if (gap < least && gap < distance(self.x - other.x, self.y - other.y)) return true;
    }
    return false;
  }

  /** Into `spot`: somewhere roomy on `body`, apart from everyone. */
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
      if (other && distance(x - other.x, y - other.y) < apart) return false;
    }
    for (const ring of this.rings) {
      if (ring.visible && distance(x - ring.x, y - ring.y) < apart) return false;
    }
    return true;
  }

  private updateHeron(heron: HeronCritter, dt: number, hour: number): void {
    const { tuning, random } = this;
    const day = inHours(hour, tuning.heronHours[0], tuning.heronHours[1]);
    heron.clock += dt;
    heron.left -= dt;
    switch (heron.state) {
      case 'away':
        heron.visible = false;
        if (heron.left <= 0 && day) this.land(heron);
        break;
      case 'arriving':
      case 'leaving': {
        const t = Math.min(1, heron.clock / FLIGHT_SECONDS);
        const going = heron.state === 'leaving';
        const near = going ? t * t : 1 - (1 - t) * (1 - t);
        const from = going ? heron.perch : heron.from;
        const to = going ? heron.from : heron.perch;
        heron.x = from.x + (to.x - from.x) * near;
        heron.y = from.y + (to.y - from.y) * near;
        heron.z = FLIGHT_METRES * (going ? near : 1 - near);
        const wings = heron.clock % (2 * WING_SECONDS) < WING_SECONDS;
        heron.frame = HERON_FRAMES[wings ? 'fly0' : 'fly1'][heron.side];
        if (t < 1) break;
        if (going) {
          heron.state = 'away';
          heron.visible = false;
          heron.left = between(tuning.heronAway, random);
        } else {
          heron.state = 'standing';
          heron.left = between(tuning.heronStays, random);
          this.poseHeron(heron, 'stand');
        }
        break;
      }
      case 'standing':
        if (!day || heron.left <= 0) {
          this.fly(heron, 'leaving');
          break;
        }
        if ((heron.poseLeft -= dt) <= 0) this.nextHeronPose(heron);
        heron.frame = HERON_FRAMES[heron.pose][heron.side];
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
      [heron.perch.x, heron.perch.y] = [perches[i], perches[i + 1]];
      const way = this.random() < 0.5 ? 1 : -1;
      [heron.from.x, heron.from.y] = [heron.perch.x + way * FLIGHT_TILES, heron.perch.y - way * FLIGHT_TILES];
      heron.side = way > 0 ? 'left' : 'right';
      this.fly(heron, 'arriving');
      return;
    }
    heron.left = between(this.tuning.heronAway, this.random) / 4;
  }

  private fly(heron: HeronCritter, state: 'arriving' | 'leaving'): void {
    heron.state = state;
    heron.visible = true;
    heron.clock = 0;
    const start = state === 'arriving' ? heron.from : heron.perch;
    heron.x = start.x;
    heron.y = start.y;
    heron.z = state === 'arriving' ? FLIGHT_METRES : 0;
    if (state === 'leaving')
      heron.side = heron.from.x - heron.from.y > heron.perch.x - heron.perch.y ? 'right' : 'left';
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
    heron.frame = HERON_FRAMES[pose][heron.side];
  }

  private ring(x: number, y: number, rise: Ripple, first: number): void {
    for (const ring of this.rings) {
      if (ring.visible) continue;
      ring.x = x;
      ring.y = y;
      ring.rise = rise;
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
    const step = ring.first + Math.floor(ring.age / RING_SECONDS);
    if (step >= RING_ALPHAS.length) {
      ring.visible = false;
      return;
    }
    ring.frame = RING_FRAMES[step === 0 ? ring.rise : RIPPLES[step + 1]];
    ring.alpha = RING_ALPHAS[step];
  }
}

const DUCK_SECONDS: Record<DuckState, Span> = {
  paddle: [6, 20],
  rest: [3, 9],
  dabble: [1.5, 3],
  under: [1.5, 3],
  preen: [2, 5],
  tucked: [0, 0],
};

const HERON_SECONDS: Record<HeronPose, Span> = {
  stand: [3, 9],
  hunch: [5, 15],
  strike: [0.4, 0.6],
  fly0: [0, 0],
  fly1: [0, 0],
};

const wrap = (angle: number) => Math.atan2(Math.sin(angle), Math.cos(angle));
