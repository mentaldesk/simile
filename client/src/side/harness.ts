// The `?harness=side` dev harness: README.md.
import Phaser from 'phaser';
import { server, type Bionic, type Body, type ClientMessage, type Entity, type Facing, type Frame, type Item, type Pose, type Position, type Recipe, type Wall } from '../net';
import { speakingSeconds } from '../ui/bubbles';
import { PLAYER_ID } from '../ui/world-view';
import { levels } from '../world/assets';
import { usedByE } from '../world/reach';
import { WALKING_SPEED } from '../world/tuning';
import worksJson from '../../../content/works/works.json';
import './harness.css';
import { glowAround, sightOf } from './darkness';
import { lampHere } from './lamp';
import { cellOf, isStanding, type Village } from './maps';
import { CLIMB_SPEED, RIDE_SPEED } from './motion';
import type { MapPosition, SidePlayer } from './player';
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
const STREETS = ['high_street', 'lychee_lane', 'kapok_walk', 'banyan_row', 'rooftops', 'metro'];
/** `lamp=on` and `charge=` set the player's lamp, which L switches as the server would. */
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: Number(params.get('charge') ?? 0.8), on: params.get('lamp') === 'on' };

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

/** Every pose, facing right, left, back and front, and Ingrid asleep in her bed. */
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
  ingrid: spot('house_10_floor_1', 2, 2, 'sleeping', 'east'),
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
    await ingrid.settle('sleeping', 'east', 8);
    await ingrid.walkTo(5);
    await ingrid.settle('looking', 'north', 3);
    await ingrid.walkTo(2);
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

/** The server's recipes the walk learns, from `simile.clinic`'s config. */
const RECIPES: Partial<Record<Bionic, Recipe>> = {
  datajack: {
    bionic: 'datajack',
    name: 'Datajack',
    parts: { copper_wire: 3, usb_c_connector: 1 },
    credits: 100,
    replaces: ['vertebra'],
    after: ['power_cell'],
  },
};

let items: Item[] = [LAMP];
let searched: string[] = [];
let known: Bionic[] = [];

/** `health=` sets how hurt the player starts; E at their bed rests them back to full in `REST_SECONDS`, as the server does. */
let health = Number(params.get('health') ?? 1);
let resting = false;
let bed: MapPosition | undefined;
const REST_SECONDS = 3;
const REST_TICK_MS = 100;

let body: Body = {
  legs: 'present',
  vertebra: 'present',
  left_eye: 'present',
  right_eye: 'present',
  left_kidney: 'present',
  right_kidney: 'present',
};

function sendPlayerState(): void {
  const mind = known.length ? { mind: { recipes: known } } : {};
  const player = { money: 0, items, carry_limit: 10, body, hunger: 0, health, ...(searched.length ? { searched } : {}), ...mind };
  const recipes = known.map((bionic) => RECIPES[bionic] ?? { bionic, name: bionic, parts: {}, credits: 0, replaces: [], after: [] });
  const rest = { ...(bed && { bed }), ...(resting && { resting }) };
  dispatch({ type: 'player_state', player, ...(recipes.length ? { recipes } : {}), ...rest });
}

/** E at something to search, as the server does it, carrying everything. */
function search(at: Position | undefined): void {
  const used = usedByE(at);
  if (used?.kind !== 'searchable') return;
  const { id, items: found = [], teaches } = used.interactable;
  searched = [...searched, id];
  items = [...items, ...found];
  if (teaches && !known.includes(teaches)) known = [...known, teaches];
  sendPlayerState();
}

/** The beds at home in the maker space, healing whoever rests in one, and ending the rest off it or at full health. */
function rests(scene: SideScene, village: Village): void {
  const beds = [...village.maps.values()]
    .filter(({ id }) => id.startsWith('maker_space'))
    .flatMap(({ id, furniture }) =>
      furniture.filter(({ name }) => name === 'bed').flatMap(({ x, y, w, h }) => [...Array(w * h).keys()].map((i) => ({ map: id, x: x + (i % w), y: y + Math.floor(i / w) }))),
    );
  setInterval(() => {
    const at = scene.playing?.mapPosition;
    const cell = at && cellOf(at);
    const here = cell && beds.find(({ map, x, y }) => map === at.map && x === cell.x && y === cell.y);
    const moved = here !== bed;
    bed = here;
    if (resting) health = Math.min(1, health + REST_TICK_MS / 1000 / REST_SECONDS);
    const wasResting = resting;
    resting &&= !!bed && health < 1;
    if (moved || wasResting) sendPlayerState();
  }, REST_TICK_MS);
}

function answer(message: ClientMessage, scene: SideScene): void {
  if (message.type === 'rest') {
    resting = message.on && !!bed && health < 1;
    return sendPlayerState();
  }
  if (message.type === 'pick_up') search(scene.playing?.mapPosition);
  if (message.type !== 'lamp' || (message.on && !LAMP.charge)) return;
  LAMP.on = message.on;
  sendPlayerState();
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
    <p>Left and right walk, Shift switches to running and back, and Space or PageUp jumps. E takes a door, or uses
    what's in reach. T talks to the ringed resident, and V looks at a mural or a painting. Up climbs stairs or a ladder from the tile beside its foot, and down from beside its
    top; up and down ride the lift. L switches the lamp. [ and ] move the clock an hour; 1 to 6 go to each
    street, 6 the metro.</p>`;
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

/** The lamp, where the player stands, and the darkness drawn over their cell. */
function lamp(player: SidePlayer, village: Village) {
  const street = village.map(village.map(player.map)!.street)!;
  const { x, y } = cellOf(player.at);
  const gloom = sightOf(street).darkness(x, y, glowAround(player.at, LAMP));
  const hint = document.querySelector<HTMLElement>('.lamp-hint');
  return { ...lampHere, on: LAMP.on, gloom, hint: hint && !hint.hidden ? hint.textContent : null };
}

/** What `walk.e2e.ts` drives the player by and checks. */
function exposeWalk(scene: SideScene, village: Village): void {
  const prompts = () =>
    [...document.querySelectorAll<HTMLElement>('.way-prompt')].filter((tag) => !tag.hidden).map((tag) => tag.ariaLabel);
  const talk = () => {
    const tag = document.querySelector<HTMLElement>('.dialogue-target-talk');
    return tag && !tag.hidden ? tag.ariaLabel : null;
  };
  Object.assign(window, {
    sideWalk: {
      state: () => {
        const player = scene.playing;
        if (!player) return undefined;
        const { map, position, climbing, drawn, airborne } = player;
        const used = usedByE(player.mapPosition)?.kind ?? null;
        const state = { map, x: position.x, y: position.y, climbing: climbing ?? null, run: drawn.run, bed: drawn.bed, running: scene.runningOn, airborne, used };
        return { ...state, prompts: prompts(), talk: talk(), lamp: lamp(player, village) };
      },
      links: () => [...village.maps.values()].flatMap(({ links }) => links),
      runs: () =>
        village.streets.flatMap((street) =>
          climbRuns(street).map(({ kind, path }) => ({ map: street.id, kind, foot: path.points[0], head: path.points.at(-1) })),
        ),
      widths: () => Object.fromEntries([...village.maps.values()].map(({ id, width }) => [id, width])),
      terminals: () =>
        village.streets.flatMap((street) =>
          street.locations
            .filter(({ type }) => type === 'terminal')
            .map(({ props }) => ({ map: street.id, x: Number(props.entry_x), y: Number(props.entry_y) })),
        ),
      counters: () =>
        [...village.maps.values()].flatMap((map) =>
          map.interactables
            .filter(({ type }) => type === 'counter')
            .map(({ x, w, props }) => {
              const [stand] = String(props.stand).split(' ').map((cell) => cell.split(',').map(Number));
              return { map: map.id, x: stand[0], y: stand[1], behind: x + Math.floor(w / 2) };
            }),
        ),
      move: (id: string, position: MapPosition) =>
        dispatch({ type: 'entity_moved', entity_id: id, position, pose: 'standing', facing: 'south' }),
      standing: (map: string, x: number, y: number) => {
        const found = village.map(map);
        return !!found && isStanding(found, x, y);
      },
      teleport: (to: MapPosition) => scene.teleport(to),
      mind: () => ({ recipes: known, searched, items: items.map(({ id }) => id) }),
      usables: () => scene.usableView.drawn(),
      levels: () => Object.fromEntries(Object.entries(levels).map(([level, { sewers }]) => [level, sewers.width])),
      pieces: (piece: string) =>
        scene.children.list
          .filter((child) => child instanceof Phaser.GameObjects.Image && child.texture.key.startsWith(`side:${piece}`))
          .map((child) => {
            const image = child as Phaser.GameObjects.Image;
            const { left, right } = image.getBounds();
            return { key: image.texture.key, width: image.frame.realWidth, left, right, visible: image.visible };
          }),
      textureLimit: () => (scene.renderer as Partial<Phaser.Renderer.WebGL.WebGLRenderer>).getMaxTextureSize?.() ?? null,
      rest: () => ({ health, resting, bed: bed ?? null }),
      hurt: (to: number) => {
        health = to;
        sendPlayerState();
      },
      fit: (part: keyof Body, bionic: Body[keyof Body]) => {
        body = { ...body, [part]: bionic };
        sendPlayerState();
      },
      jacks: () =>
        [...village.maps.values()].flatMap((map) =>
          map.interactables
            .filter(({ type }) => type === 'jack')
            .flatMap(({ props }) =>
              String(props.stand)
                .split(' ')
                .map((cell) => cell.split(',').map(Number))
                .map(([x, y]) => ({ map: map.id, x, y })),
            ),
        ),
    },
  });
}

export function startHarness(scene: SideScene, village: Village): void {
  server.close();
  server.send = (message) => {
    console.info('Side harness: sent', message);
    answer(message, scene);
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
  const level = Number(params.get('level') ?? 0);
  dispatch({ type: 'snapshot', time: clockAt(hour), map_id: map, entities, conversations: [], level });
  dispatch({ type: 'clock', time: clockAt(hour), speed: SPEED });
  if (params.get('murals') !== '0') dispatch({ type: 'murals', walls: walls(village) });
  dispatch({ type: 'paintings', frames: frames(village) });
  sendPlayerState();
  if (!params.has('still')) {
    direct(all, village);
    chat();
  }
  showPanel();
  measure(scene);
  exposeWalk(scene, village);
  rests(scene, village);
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
