// The `?harness=side` dev harness: README.md.
import Phaser from 'phaser';
import { server, type Entity, type Facing, type Frame, type Pose, type Position, type Wall } from '../net';
import { speakingSeconds } from '../ui/bubbles';
import { PLAYER_ID } from '../ui/world-view';
import { WALKING_SPEED } from '../world/tuning';
import worksJson from '../../../content/works/works.json';
import './harness.css';
import type { Village } from './maps';
import { CLIMB_SPEED, RIDE_SPEED } from './motion';
import type { MapPosition } from './player';
import { climbRuns, crossing, type Path } from './runs';
import type { SideScene } from './side-scene';

const pictures = import.meta.glob<string>('../../../content/works/*.png', {
  eager: true,
  query: '?url',
  import: 'default',
});
const works = worksJson as { id: string; artist: string; medium: string; title: string; statement: string; wall?: string }[];

const params = new URLSearchParams(location.search);
const START_HOUR = Number(params.get('hour') ?? 10);
const SPEED = Number(params.get('speed') ?? 60);
const STREETS = ['high_street', 'lychee_lane', 'kapok_walk', 'banyan_row'];

const sleep = (seconds: number) => new Promise((resolve) => setTimeout(resolve, seconds * 1000));
const dispatch = (message: object) => server.dispatch(JSON.stringify(message));

const NAMES: Record<string, string> = {
  desmond: 'Desmond',
  henrietta: 'Henrietta',
  ingrid: 'Ingrid',
  kofi: 'Kofi',
  lachlan: 'Lachlan',
  marguerite: 'Marguerite',
  mirela: 'Mirela',
  odalys: 'Odalys',
  priya: 'Priya',
  raymond: 'Raymond',
  tobias: 'Tobias',
};

type Spot = MapPosition & { pose: Pose; facing: Facing };
const spot = (map: string, x: number, y: number, pose: Pose, facing: Facing): Spot => ({ map, x, y, pose, facing });

/** Every pose, facing right, left, back and front. */
const STARTS: Record<string, Spot> = {
  kofi: spot('high_street', 30, 15, 'walking', 'east'),
  priya: spot('high_street', 48, 15, 'sitting', 'south'),
  henrietta: spot('high_street', 49, 15, 'reading', 'south'),
  lachlan: spot('high_street', 28, 15, 'looking', 'north'),
  odalys: spot('coffee_shop_floor_0', 12, 2, 'standing', 'west'),
  mirela: spot('coffee_shop_floor_0', 3, 2, 'working', 'north'),
  desmond: spot('maker_space_floor_1', 3, 2, 'working', 'north'),
  raymond: spot('kapok_walk', 4, 15, 'sitting', 'south'),
  marguerite: spot('lychee_lane', 43, 15, 'standing', 'east'),
  tobias: spot('banyan_row', 47, 15, 'standing', 'east'),
  ingrid: spot('gallery_floor_0', 10, 2, 'looking', 'north'),
};

class Puppet {
  readonly id: string;
  at: Spot;
  private readonly village: Village;

  constructor(id: string, at: Spot, village: Village) {
    this.id = id;
    this.at = { ...at };
    this.village = village;
  }

  send(position: MapPosition, pose: Pose, facing: Facing): void {
    this.at = { ...position, pose, facing };
    dispatch({ type: 'entity_moved', entity_id: this.id, position, pose, facing });
  }

  async settle(pose: Pose, facing: Facing, seconds: number): Promise<void> {
    this.send(this.at, pose, facing);
    await sleep(seconds);
  }

  async walkTo(x: number): Promise<void> {
    const way = Math.sign(x - this.at.x);
    const facing: Facing = way < 0 ? 'west' : 'east';
    while (this.at.x !== x) {
      this.send({ ...this.at, x: this.at.x + way }, 'walking', facing);
      await sleep(1 / WALKING_SPEED);
    }
    this.send(this.at, 'standing', facing);
  }

  async climb(path: Path): Promise<void> {
    const points = path.points[0].x === this.at.x && path.points[0].y === this.at.y ? path.points : [...path.points].reverse();
    for (let i = 1; i < points.length; i++) {
      const [a, b] = [points[i - 1], points[i]];
      const end = i === points.length - 1;
      const facing: Facing = b.x === a.x ? 'north' : b.x > a.x ? 'east' : 'west';
      this.send({ map: this.at.map, x: b.x, y: b.y }, end ? 'walking' : 'climbing', facing);
      const kind = a.x === b.x ? 'ladder' : 'stairs';
      await sleep(Math.hypot(b.x - a.x, b.y - a.y) / CLIMB_SPEED[kind]);
    }
  }

  async cross(): Promise<void> {
    const link = this.village.linkAt(this.at.map, this.at.x, this.at.y);
    const across = link && crossing(this.village, link);
    if (!across) return;
    const riding = across.kind === 'lift';
    this.send(this.at, riding ? 'riding' : 'climbing', riding ? 'south' : this.at.facing);
    const speed = riding ? RIDE_SPEED : CLIMB_SPEED[across.kind as 'stairs' | 'ladder'];
    await sleep(across.path.total / speed + 0.2);
    this.send({ map: across.to.map, x: across.to.x, y: across.to.y }, 'standing', this.at.facing);
  }
}

async function forever(step: () => Promise<void>): Promise<void> {
  for (;;) await step();
}

function puppets(village: Village): Record<string, Puppet> {
  return Object.fromEntries(Object.entries(STARTS).map(([id, at]) => [id, new Puppet(id, at, village)]));
}

function direct(all: Record<string, Puppet>, village: Village): void {
  const { kofi, odalys, desmond, marguerite, tobias, ingrid } = all;
  void forever(async () => {
    await kofi.walkTo(62);
    await kofi.settle('standing', 'west', 2);
    await kofi.walkTo(30);
    await kofi.settle('standing', 'east', 2);
  });
  void forever(async () => {
    await odalys.walkTo(15);
    await odalys.cross();
    await odalys.walkTo(3);
    await odalys.settle('sitting', 'east', 6);
    await odalys.walkTo(11);
    await odalys.cross();
    await odalys.walkTo(12);
    await odalys.settle('standing', 'west', 3);
  });
  void forever(async () => {
    await desmond.settle('working', 'north', 6);
    await desmond.walkTo(6);
    await desmond.cross();
    await desmond.settle('looking', 'south', 4);
    await desmond.cross();
    await desmond.walkTo(3);
  });
  const [ladder] = climbRuns(village.map('lychee_lane')!);
  void forever(async () => {
    await marguerite.walkTo(45);
    await marguerite.climb(ladder.path);
    await marguerite.walkTo(47);
    await marguerite.settle('looking', 'south', 5);
    await marguerite.walkTo(46);
    await marguerite.climb(ladder.path);
    await marguerite.walkTo(40);
    await marguerite.settle('standing', 'east', 2);
  });
  const [steps] = climbRuns(village.map('banyan_row')!);
  void forever(async () => {
    await tobias.walkTo(53);
    await tobias.climb(steps.path);
    await tobias.walkTo(60);
    await tobias.settle('reading', 'north', 5);
    await tobias.walkTo(56);
    await tobias.climb(steps.path);
    await tobias.walkTo(47);
    await tobias.settle('looking', 'north', 4);
  });
  void forever(async () => {
    await ingrid.settle('looking', 'north', 3);
    await ingrid.walkTo(16);
    await ingrid.cross();
    await ingrid.walkTo(8);
    await ingrid.settle('looking', 'north', 4);
    await ingrid.walkTo(15);
    await ingrid.cross();
    await ingrid.walkTo(10);
  });
}

function chat(): void {
  const lines: [string, string][] = [
    ['priya', 'The fountain sounds louder at this hour.'],
    ['henrietta', "That's the pump. Someone's fixed it again."],
    ['priya', 'Kofi says he wants a mural on the tower next.'],
    ['henrietta', 'Kofi says a lot of things.'],
  ];
  let id = 9000;
  void forever(async () => {
    for (const [speaker, text] of lines) {
      const duration = speakingSeconds(text);
      dispatch({
        type: 'line',
        voiced: false,
        line: { id: id++, conversation_id: 'side-harness', speaker, text, timestamp: new Date().toISOString(), duration },
      });
      await sleep(duration + 1);
    }
  });
}

function walls(village: Village): Wall[] {
  const murals = works.filter(({ medium }) => medium === 'mural');
  return village.streets.flatMap((street) =>
    street.murals.map((wall, i): Wall => {
      const work = murals.find((mural) => mural.wall === wall.name) ?? murals[i % murals.length];
      return {
        id: wall.name,
        map: street.id,
        x: wall.x,
        y: wall.y,
        width: wall.w,
        face: 'south',
        bottom: Number(wall.props.bottom),
        top: Number(wall.props.top),
        mural: {
          work_id: work.id,
          title: work.title,
          artist: { id: work.artist, name: NAMES[work.artist] ?? work.artist },
          statement: work.statement,
          image: pictures[`../../../content/works/${work.id}.png`],
        },
      };
    }),
  );
}

function frames(village: Village): Frame[] {
  const paintings = works.filter(({ medium }) => medium === 'painting');
  return village.floors('gallery').flatMap((floor) =>
    floor.interactables
      .filter(({ type }) => type === 'painting')
      .map(({ name }, i): Frame => {
        const work = paintings[(i + floor.floor * 2) % paintings.length];
        return {
          id: name,
          map: floor.id,
          painting:
            i === 2
              ? null
              : {
                  work_id: work.id,
                  title: work.title,
                  artist: { id: work.artist, name: NAMES[work.artist] ?? work.artist },
                  statement: work.statement,
                  image: pictures[`../../../content/works/${work.id}.png`],
                },
        };
      }),
  );
}

function clockAt(hour: number): string {
  const date = new Date(Date.UTC(2026, 9, 21, 0, 0, 0) + hour * 3_600_000);
  return date.toISOString();
}

function showPanel(): void {
  if (params.get('panel') === '0') return;
  const panel = document.body.appendChild(document.createElement('section'));
  panel.className = 'side-harness';
  panel.innerHTML = `<b>Side-view harness</b>
    <p>Left and right walk. E or up takes a door. E gets on stairs or a ladder, then up and down
    climb; E rides a lift. [ and ] move the clock an hour; 1 to 4 go to each street.</p>`;
}

/** Work from each step's start to the end of its render, and the gaps between frames. */
function measure(scene: Phaser.Scene): void {
  const times = new Float64Array(600);
  const gaps = new Float64Array(600);
  let count = 0;
  let begun = 0;
  let last = 0;
  scene.game.events.on(Phaser.Core.Events.PRE_STEP, () => (begun = performance.now()));
  scene.game.events.on(Phaser.Core.Events.POST_RENDER, () => {
    const now = performance.now();
    gaps[count % gaps.length] = now - last;
    times[count++ % times.length] = now - begun;
    last = now;
  });
  const stats = (values: Float64Array) => {
    const all = [...values.slice(0, Math.min(count, values.length))].sort((a, b) => a - b);
    const at = (q: number) => all[Math.min(all.length - 1, Math.floor(q * all.length))];
    return { median: at(0.5), p95: at(0.95), max: all.at(-1) };
  };
  Object.assign(window, {
    sideScene: scene,
    sideFrameTimes: () => ({ frames: Math.min(count, times.length), work: stats(times), gap: stats(gaps) }),
  });
}

export function startHarness(scene: SideScene, village: Village): void {
  server.close();
  server.send = (message) => {
    console.info('Side harness: sent', message);
    return true;
  };
  const [map, x, y] = (params.get('at') ?? 'high_street:51:15').split(':');
  const player: Position = { map, x: Number(x), y: Number(y ?? (village.map(map)?.kind === 'floor' ? 2 : 15)) };
  const all = puppets(village);
  const entities: Entity[] = [
    { id: PLAYER_ID, kind: 'player', name: 'You', position: player, pose: 'standing', facing: 'east' },
    ...Object.values(all).map(({ id, at }): Entity => ({
      id,
      kind: 'npc',
      name: NAMES[id],
      position: { map: at.map, x: at.x, y: at.y },
      pose: at.pose,
      facing: at.facing,
    })),
  ];
  let hour = START_HOUR;
  let setAt = performance.now();
  dispatch({ type: 'snapshot', time: clockAt(hour), map_id: map, entities, conversations: [] });
  dispatch({ type: 'clock', time: clockAt(hour), speed: SPEED });
  if (params.get('murals') !== '0') dispatch({ type: 'murals', walls: walls(village) });
  dispatch({ type: 'paintings', frames: frames(village) });
  if (!params.has('still')) {
    direct(all, village);
    chat();
  }
  showPanel();
  measure(scene);
  window.addEventListener('keydown', ({ key }) => {
    if (key === '[' || key === ']') {
      const now = performance.now();
      hour += ((now - setAt) / 1000 / 3600) * SPEED + (key === ']' ? 1 : -1);
      setAt = now;
      dispatch({ type: 'clock', time: clockAt(hour), speed: SPEED });
    }
    const street = STREETS[Number(key) - 1];
    const to = street && village.map(street);
    if (to) scene.teleport({ map: street, x: Math.floor(to.width / 2), y: 15 });
  });
}
