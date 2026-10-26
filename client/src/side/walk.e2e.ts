// The player's walk through the side view in Chromium, by the keys: README.md's "The walk" says what and how to run it.
import { chromium, type Page } from 'playwright';
import { createServer } from 'vite';

declare const process: { argv: string[]; platform: string; exitCode?: number };

type Cell = { x: number; y: number };
type Place = Cell & { map: string };
type Link = Place & { id: string; kind: 'door' | 'stairs' | 'ladder' | 'lift'; side: 'inside' | 'outside'; to: Place };
type Run = { map: string; kind: string; foot: Cell; head: Cell };
type Counter = Place & { behind: number };
type State = Place & {
  climbing: string | null;
  run: number;
  airborne: boolean;
  used: string | null;
  prompts: string[];
  talk: string | null;
  lamp: { dark: boolean; plug: boolean; on: boolean; gloom: number; hint: string | null };
};
type SideWalk = {
  state(): State | undefined;
  links(): Link[];
  runs(): Run[];
  widths(): Record<string, number>;
  terminals(): Place[];
  counters(): Counter[];
  standing(map: string, x: number, y: number): boolean;
  teleport(to: Place): void;
  move(id: string, to: Place): void;
  fit(part: string, bionic: string): void;
  jacks(): Place[];
};
type Paged = { sideWalk: SideWalk };
type Hold = 'ArrowUp' | 'ArrowDown';
/** Walk from `start` to within `reach` of `x` on its row, then press E or hold up or down, and arrive at `arrive`. */
type Leg = { name: string; start: Place; x: number; reach: number; key: 'e' | Hold; arrive: Place };

const args = process.argv.slice(2);
const option = (name: string) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);
const screens = option('--screens');
const realTime = args.includes('--real-time');
const FRAME_MS = 1000 / 60;
const SECONDS_TO_ARRIVE = 12;
/** On the cell of a door or a lift; near the far edge of the tile beside a flight's or a ladder's end. */
const REACH = { cell: 0.45, edge: 1.4 };
/** The client's `PLAYER_SPEED` and `RUN_PACE`. */
const WALK_SPEED = 2.6;
const RUN_PACE = 2;
const PROMPT_KEY = { e: 'E', ArrowUp: '↑', ArrowDown: '↓' } as const;

const walkApi = (page: Page) => ({
  state: () => page.evaluate(() => (window as unknown as Paged).sideWalk.state()),
  links: () => page.evaluate(() => (window as unknown as Paged).sideWalk.links()),
  runs: () => page.evaluate(() => (window as unknown as Paged).sideWalk.runs()),
  widths: () => page.evaluate(() => (window as unknown as Paged).sideWalk.widths()),
  terminals: () => page.evaluate(() => (window as unknown as Paged).sideWalk.terminals()),
  counters: () => page.evaluate(() => (window as unknown as Paged).sideWalk.counters()),
  standing: (place: Place) =>
    page.evaluate(({ map, x, y }) => (window as unknown as Paged).sideWalk.standing(map, x, y), place),
  teleport: (to: Place) => page.evaluate((to) => (window as unknown as Paged).sideWalk.teleport(to), to),
  move: (id: string, to: Place) =>
    page.evaluate(([id, to]) => (window as unknown as Paged).sideWalk.move(id, to), [id, to] as const),
  fit: (part: string, bionic: string) =>
    page.evaluate(([part, bionic]) => (window as unknown as Paged).sideWalk.fit(part, bionic), [part, bionic] as const),
  jacks: () => page.evaluate(() => (window as unknown as Paged).sideWalk.jacks()),
});
type Api = ReturnType<typeof walkApi>;

async function run(page: Page, ms: number): Promise<void> {
  if (realTime) await page.waitForTimeout(ms);
  else await page.clock.runFor(Math.ceil(ms / FRAME_MS) * FRAME_MS);
}

async function until(page: Page, check: () => Promise<boolean>, seconds: number, what: string, step = 100) {
  for (let waited = 0; waited < seconds * 1000; waited += step) {
    if (await check()) return;
    await run(page, step);
    if (!realTime) await page.waitForTimeout(10);
  }
  throw new Error(`${what}: not within ${seconds} s`);
}

const near = (state: State | undefined, place: Place, by = 0.01) =>
  !!state && state.map === place.map && Math.abs(state.x - place.x) <= by && Math.abs(state.y - place.y) <= by;

const floorOf = (map: string) => Number(/_floor_(\d+)$/.exec(map)?.[1] ?? NaN);

/** A standing cell two tiles from `end` along its row, towards the middle of the map, to walk from. */
async function startFor(api: Api, end: Place, width: number): Promise<Place> {
  const towards = end.x < width / 2 ? 1 : -1;
  for (const step of [2, -2, 1, -1]) {
    const x = end.x + towards * step;
    if (await api.standing({ map: end.map, x, y: end.y })) return { map: end.map, x, y: end.y };
  }
  return end;
}

async function teleport(page: Page, api: Api, to: Place, what: string): Promise<void> {
  for (let tries = 1; ; tries++) {
    await api.teleport(to);
    try {
      await until(page, async () => near(await api.state(), to), 10, `${what}: getting to ${JSON.stringify(to)}`);
      return;
    } catch (error) {
      if (tries === 3) throw error;
    }
  }
}

/** Doors on E; stairs and ladders up from their foot on up and down from their top on down; the lift a floor up on
 * up and a floor down on down, from each of its cells. A link from a jack waits for the datajack, in `bionicsLeg`. */
async function legs(api: Api): Promise<Leg[]> {
  const [links, widths, jacks] = [await api.links(), await api.widths(), await api.jacks()];
  const jacked = (link: Link) => jacks.some(({ map, x, y }) => map === link.map && x === link.x && y === link.y);
  const far = (link: Link) => links.find(({ map, x, y }) => map === link.to.map && x === link.to.x && y === link.to.y)!;
  const found: Leg[] = [];
  for (const link of links.filter((link) => !jacked(link))) {
    const there = far(link);
    const arrive = { map: there.map, x: there.x, y: there.y };
    const start = await startFor(api, link, widths[link.map]);
    const leg = { start, x: link.x, arrive };
    if (link.kind === 'door') {
      const [inside, goingIn] = [link.map.includes('_floor_'), there.map.includes('_floor_')];
      const name = goingIn ? `into ${there.map}` : inside ? `out of ${link.map}` : `${link.map} to ${there.map}`;
      found.push({ ...leg, name, reach: REACH.cell, key: 'e' });
    } else if (link.kind === 'lift') {
      for (const up of [true, false]) {
        const next = links.find(
          (other) => other.kind === 'lift' && other.map === link.map && floorOf(other.to.map) === floorOf(link.map) + (up ? 1 : -1),
        );
        if (!next) continue;
        const to = far(next);
        const name = `lift ${up ? 'up' : 'down'} from ${link.map} at ${link.x}`;
        found.push({ ...leg, name, reach: REACH.cell, key: up ? 'ArrowUp' : 'ArrowDown', arrive: { map: to.map, x: to.x, y: to.y } });
      }
    } else {
      const up = link.side === 'outside';
      found.push({ ...leg, name: `${link.id} ${up ? 'up' : 'down'} from ${link.map}`, reach: REACH.edge, key: up ? 'ArrowUp' : 'ArrowDown' });
    }
  }
  for (const run of await api.runs()) {
    for (const [from, to, up] of [
      [run.foot, run.head, true],
      [run.head, run.foot, false],
    ] as const) {
      const start = await startFor(api, { map: run.map, ...from }, widths[run.map]);
      const name = `${run.kind} on ${run.map} ${up ? 'up' : 'down'} from ${from.x}, ${from.y}`;
      found.push({ name, start, x: from.x, reach: REACH.edge, key: up ? 'ArrowUp' : 'ArrowDown', arrive: { map: run.map, ...to } });
    }
  }
  return found;
}

async function shot(page: Page, index: number, name: string): Promise<void> {
  if (!screens) return;
  const path = `${screens}/${String(index).padStart(3, '0')}-${name.replaceAll(/\W+/g, '-')}.jpg`;
  await page.screenshot({ path, type: 'jpeg', quality: 80 });
}

/** E where nothing takes it leaves the player where they are. */
async function pressingE(page: Page, api: Api, name: string): Promise<void> {
  const before = (await api.state())!;
  await page.keyboard.press('e');
  await run(page, 500);
  const after = (await api.state())!;
  if (after.climbing || after.map !== before.map || Math.abs(after.x - before.x) > 1e-6 || after.y !== before.y) {
    throw new Error(`${name}: E moved the player from ${JSON.stringify(before)} to ${JSON.stringify(after)}`);
  }
}

/** Says whether E was pressed first, to no effect. */
async function walkLeg(page: Page, api: Api, leg: Leg, index: number): Promise<string | void> {
  await teleport(page, api, leg.start, leg.name);
  await run(page, 300);
  const state = (await api.state())!;
  if (Math.abs(state.x - leg.x) > leg.reach) {
    const walk = leg.x > state.x ? 'ArrowRight' : 'ArrowLeft';
    await page.keyboard.down(walk);
    const there = async () => Math.abs((await api.state())!.x - leg.x) <= leg.reach;
    await until(page, there, 5, `${leg.name}: walking to within ${leg.reach} of ${leg.x}`, FRAME_MS);
    await page.keyboard.up(walk);
  }
  await run(page, 200);
  const { prompts, x, used, talk } = (await api.state())!;
  if (leg.reach === REACH.edge && Math.abs(x - leg.x) < 1.3) {
    throw new Error(`${leg.name}: stopped ${Math.abs(x - leg.x).toFixed(2)} from ${leg.x}, not at the edge of its reach`);
  }
  const key = PROMPT_KEY[leg.key];
  if (!prompts.some((prompt) => prompt.split(':')[0].split(' ').includes(key))) {
    throw new Error(`${leg.name}: no prompt for ${key} at ${leg.x}, only ${JSON.stringify(prompts)}`);
  }
  await shot(page, index, leg.name);
  const eFree = !used && !talk && !prompts.some((prompt) => prompt.split(':')[0].split(' ').includes('E'));
  if (leg.key === 'e') await page.keyboard.press('e');
  else {
    if (eFree) await pressingE(page, api, leg.name);
    await page.keyboard.down(leg.key);
  }
  const arrive = `${leg.name}: arriving at ${JSON.stringify(leg.arrive)}`;
  await until(page, async () => near(await api.state(), leg.arrive), SECONDS_TO_ARRIVE, arrive);
  if (leg.key !== 'e') await page.keyboard.up(leg.key);
  if (leg.key !== 'e' && eFree) return 'E first did nothing';
}

/** Along the High Street, walking, then running from a press of Shift, then walking from another. */
async function runLeg(page: Page, api: Api, index: number): Promise<void> {
  await teleport(page, api, { map: 'high_street', x: 2, y: 15 }, 'running');
  await page.keyboard.down('ArrowRight');
  const along = async (ms: number) => {
    const from = (await api.state())!.x;
    await run(page, ms);
    return (await api.state())!.x - from;
  };
  const walked = await along(1000);
  await page.keyboard.press('Shift');
  await run(page, 400);
  const ran = await along(1000);
  const { run: running } = (await api.state())!;
  await shot(page, index, 'running on the High Street');
  await page.keyboard.press('Shift');
  await run(page, 400);
  const after = await along(1000);
  await page.keyboard.up('ArrowRight');
  const { run: walking } = (await api.state())!;
  const speeds = `walked ${walked.toFixed(2)}, ran ${ran.toFixed(2)}, then ${after.toFixed(2)} tiles a second`;
  if (Math.abs(walked - WALK_SPEED) > 0.15 || Math.abs(after - WALK_SPEED) > 0.15) throw new Error(`running: ${speeds}`);
  if (Math.abs(ran - RUN_PACE * WALK_SPEED) > 0.25 || running !== 1 || walking !== 0) {
    throw new Error(`running: ${speeds}, blend ${running} running and ${walking} after`);
  }
}

/** Over a gap: from `from`, right until past `takeOff`, then Space, landing past `land` on row `onto`, or else `from`'s. */
type Jump = { name: string; from: Place; takeOff: number; land: number; run: boolean; onto?: number };

const roof = (x: number, y: number): Place => ({ map: 'rooftops', x, y });
const metro = (x: number, y: number): Place => ({ map: 'metro', x, y });
const JUMPS: Jump[] = [
  { name: 'over the one-cell gap from the bakery', from: roof(6, 12), takeOff: 9.4, land: 10.75, run: false },
  { name: 'over the two-cell gap to the tea house', from: roof(18, 8), takeOff: 21.6, land: 23.25, run: false },
  { name: 'over the three-cell gap to the laundry, running', from: roof(26, 8), takeOff: 30.3, land: 33.25, run: true },
  { name: 'from the landing onto the catwalk over the stairwell', from: metro(1, 9), takeOff: 4, land: 6.5, onto: 7, run: true },
  { name: "from the train's roof onto the catwalk in the vault", from: metro(38, 12), takeOff: 42.3, land: 44.75, onto: 10, run: true },
  { name: 'up the tunnel wall from the pipe ledge', from: metro(76, 12), takeOff: 78.3, land: 80.75, onto: 10, run: true },
];
/** A run jump at the metro's high ledge, a row higher than the jump, falls back to the floor. */
const SHORT: Jump = { name: 'at the high ledge, short of it', from: metro(101, 15), takeOff: 105, land: 104, onto: 15, run: true };
/** The same on the spring feet lands on it, on the secret's cell, from a run-up long enough to see it's running. */
const LEDGE: Jump = { name: 'onto the high ledge on the spring feet', from: metro(96, 15), takeOff: 103, land: 106, onto: 12, run: true };
/** West along the gantry under its roof and over its gap, which only the legs clear, to the nook past `land`. */
const GANTRY: Jump = { name: "across the gantry's gap on the bionic legs", from: metro(72, 8), takeOff: 69, land: 63.75, onto: 8, run: true };
const GANTRY_SECRET = 61;
const SEWERS: Place = { map: 'sewers', x: 2, y: 15 };
const sewers = (x: number, y: number): Place => ({ map: 'sewers', x, y });
/** The server's `WEIR_AT`: the gate's weir is this many cells into its hall, on row 12. */
const WEIR_AT = 12;

/** Jumps a gap on the rooftops with Space held, and lands on the far side rather than in the lane. */
async function jumpLeg(page: Page, api: Api, jump: Jump, index: number): Promise<void> {
  await teleport(page, api, jump.from, jump.name);
  await run(page, 200);
  if (jump.run) await page.keyboard.press('Shift');
  await run(page, 100);
  await page.keyboard.down('ArrowRight');
  const atEdge = async () => (await api.state())!.x >= jump.takeOff;
  await until(page, atEdge, 5, `${jump.name}: running up to ${jump.takeOff}`, FRAME_MS);
  await page.keyboard.down(' ');
  await until(page, async () => (await api.state())!.airborne, 1, `${jump.name}: taking off`, FRAME_MS);
  await run(page, 200);
  await shot(page, index, jump.name);
  await until(page, async () => !(await api.state())!.airborne, 3, `${jump.name}: landing`, FRAME_MS);
  await page.keyboard.up(' ');
  await page.keyboard.up('ArrowRight');
  if (jump.run) await page.keyboard.press('Shift');
  await run(page, 100);
  const landed = (await api.state())!;
  const row = jump.onto ?? jump.from.y;
  if (landed.map !== jump.from.map || landed.y !== row || landed.x < jump.land) {
    throw new Error(`${jump.name}: landed at ${landed.x.toFixed(2)}, ${landed.y}, not on row ${row} past ${jump.land}`);
  }
}

/** Walks along the row, running, to within `reach` of `x`. */
async function walkTo(page: Page, api: Api, x: number, reach: number, what: string): Promise<void> {
  const from = (await api.state())!.x;
  if (Math.abs(from - x) <= reach) return;
  const key = x > from ? 'ArrowRight' : 'ArrowLeft';
  await page.keyboard.down(key);
  await until(page, async () => Math.abs((await api.state())!.x - x) <= reach, 40, `${what}: walking to ${x}`, FRAME_MS);
  await page.keyboard.up(key);
  await run(page, 200);
}

/** Presses E, or holds up or down, until the player is at `arrive`. */
async function take(page: Page, api: Api, key: 'e' | Hold, arrive: Place, what: string): Promise<void> {
  if (key === 'e') await page.keyboard.press('e');
  else await page.keyboard.down(key);
  await until(page, async () => near(await api.state(), arrive), SECONDS_TO_ARRIVE, `${what}: arriving at ${JSON.stringify(arrive)}`);
  if (key !== 'e') await page.keyboard.up(key);
  await run(page, 300);
}

/** From Banyan Row down through the metro into the clinic and back, by the keys alone. */
async function metroLeg(page: Page, walk: Api, index: number): Promise<void> {
  const name = 'through the metro and back';
  await teleport(page, walk, { map: 'banyan_row', x: 59, y: 18 }, name);
  await run(page, 300);
  await page.keyboard.press('Shift');
  await walkTo(page, walk, 62, REACH.cell, name);
  await take(page, walk, 'e', metro(2, 9), `${name}, down the stairway`);
  await shot(page, index, 'into the metro');
  await walkTo(page, walk, 4, REACH.edge, name);
  await take(page, walk, 'ArrowDown', metro(7, 12), `${name}, down to the ticket hall`);
  await walkTo(page, walk, 19, REACH.edge, name);
  await take(page, walk, 'ArrowDown', metro(22, 15), `${name}, down to the platform`);
  await walkTo(page, walk, 89, REACH.cell, name);
  await shot(page, index, 'at the clinic');
  await take(page, walk, 'e', { map: 'clinic_floor_0', x: 1, y: 2 }, `${name}, into the clinic`);
  await take(page, walk, 'e', metro(89, 15), `${name}, out of the clinic`);
  await walkTo(page, walk, 22, REACH.edge, name);
  await take(page, walk, 'ArrowUp', metro(19, 12), `${name}, up to the ticket hall`);
  await walkTo(page, walk, 7, REACH.edge, name);
  await take(page, walk, 'ArrowUp', metro(4, 9), `${name}, up to the landing`);
  await walkTo(page, walk, 2, REACH.cell, name);
  await take(page, walk, 'e', { map: 'banyan_row', x: 62, y: 18 }, `${name}, up to Banyan Row`);
  await page.keyboard.press('Shift');
}

/** Into the metro's dark west tunnel, the lamp on with L, and on to the plug, where it charges. */
async function lampLeg(page: Page, api: Api, index: number): Promise<void> {
  const name = 'through the dark with the lamp';
  const lamp = async () => (await api.state())!.lamp;
  const fail = async (what: string) => new Error(`${name}: ${what}, ${JSON.stringify(await lamp())}`);
  await teleport(page, api, metro(55, 15), name);
  await run(page, 300);
  if ((await lamp()).dark) throw await fail('dark on the platform');
  await walkTo(page, api, 61, REACH.cell, name);
  const dark = await lamp();
  if (!dark.dark || dark.on || dark.gloom < 0.5 || !dark.hint?.includes('Press L')) throw await fail('not dark in the tunnel');
  await page.keyboard.press('l');
  await run(page, 300);
  const lit = await lamp();
  if (!lit.on || lit.gloom > 0 || lit.hint) throw await fail("L didn't light the lamp");
  await shot(page, index, name);
  await walkTo(page, api, 72, REACH.cell, name);
  const plug = await lamp();
  if (!plug.plug || plug.dark || plug.hint !== 'Charging your lamp.') throw await fail('not charging at the plug');
  await page.keyboard.press('l');
  await run(page, 300);
  if ((await lamp()).on) throw await fail("L didn't switch the lamp off");
}

/** Walks off the clock house's roof and lands in the lane, a fall of eleven rows. */
async function fallLeg(page: Page, api: Api, index: number): Promise<void> {
  const name = "off the clock house's roof";
  await teleport(page, api, { map: 'rooftops', x: 52, y: 4 }, name);
  await page.keyboard.down('ArrowRight');
  await until(page, async () => (await api.state())!.airborne, 3, `${name}: walking off`, FRAME_MS);
  await page.keyboard.up('ArrowRight');
  await run(page, 300);
  await shot(page, index, name);
  await until(page, async () => !(await api.state())!.airborne, 3, `${name}: landing`, FRAME_MS);
  const landed = (await api.state())!;
  if (landed.y !== 15) throw new Error(`${name}: landed on row ${landed.y}, not the lane`);
}

/** What's fitted on the legs and the feet, each their own where it's left out. */
type Kit = { legs?: string; feet?: string };

async function fitKit(api: Api, kit: Kit): Promise<void> {
  await api.fit('legs', kit.legs ?? 'present');
  await api.fit('feet', kit.feet ?? 'present');
}

/** On `kit`, runs `way` from `jump.from`, jumps past `takeOff` with Space held and lands past `land` on row `onto`. */
async function legsJump(page: Page, api: Api, kit: Kit, jump: Jump, way: 1 | -1, index: number): Promise<void> {
  const past = (x: number, edge: number) => (way > 0 ? x >= edge : x <= edge);
  const key = way > 0 ? 'ArrowRight' : 'ArrowLeft';
  await fitKit(api, kit);
  await teleport(page, api, jump.from, jump.name);
  await page.keyboard.down(key);
  await run(page, 100);
  const walking = (await api.state())!.run < 0.5;
  if (walking) await page.keyboard.press('Shift');
  await until(page, async () => past((await api.state())!.x, jump.takeOff), 5, `${jump.name}: running up`, FRAME_MS);
  await page.keyboard.down(' ');
  await until(page, async () => (await api.state())!.airborne, 1, `${jump.name}: taking off`, FRAME_MS);
  await run(page, 200);
  await shot(page, index, jump.name);
  await until(page, async () => !(await api.state())!.airborne, 3, `${jump.name}: landing`, FRAME_MS);
  await page.keyboard.up(' ');
  await page.keyboard.up(key);
  if (walking) await page.keyboard.press('Shift');
  const landed = (await api.state())!;
  if (landed.y !== jump.onto || !past(landed.x, jump.land)) {
    throw new Error(`${jump.name}: landed at ${landed.x.toFixed(2)}, ${landed.y}, not on row ${jump.onto} past ${jump.land}`);
  }
}

/** E at the metro's jacks: dead without the datajack. The feet and the legs reach two secrets, and the datajack takes the lift. */
async function bionicsLeg(page: Page, api: Api, index: number): Promise<void> {
  const name = 'the bionics at the depot';
  for (const [x, label] of [
    [100, 'maintenance lift'],
    [104, 'dead terminal'],
  ] as const) {
    await teleport(page, api, metro(x, 15), `${name}, at the ${label}`);
    await run(page, 300);
    const hint = await shown(page, '.counter-hint');
    if (hint !== `Press E to use the ${label}.`) throw new Error(`${name}: at the ${label}, the hint is ${hint}`);
    await pressingE(page, api, `${name}, E at the ${label}`);
    const dead = await shown(page, '.counter-hint');
    if (dead !== `Nothing happens: the ${label} needs a datajack.`) throw new Error(`${name}: E at the ${label} said ${dead}`);
    await run(page, 2600);
  }
  await legsJump(page, api, { feet: 'spring_feet' }, LEDGE, 1, index);
  await legsJump(page, api, { legs: 'bionic_legs' }, GANTRY, -1, index);
  await walkTo(page, api, GANTRY_SECRET, REACH.cell, `${GANTRY.name}, to the secret`);
  await api.fit('vertebra', 'datajack');
  await teleport(page, api, metro(98, 15), name);
  await run(page, 300);
  await walkTo(page, api, 100, REACH.cell, name);
  await shot(page, index, 'at the lift with the datajack');
  await take(page, api, 'e', SEWERS, `${name}, down the lift to the sewers`);
  await take(page, api, 'e', metro(100, 15), `${name}, up the lift to the metro`);
}

/** A standing jump at the face of the weir, walking towards it: where it lands. */
async function atTheWeir(page: Page, api: Api, weir: number, name: string): Promise<State> {
  await teleport(page, api, sewers(weir - 1, 15), name);
  await run(page, 300);
  if ((await api.state())!.run > 0) await page.keyboard.press('Shift');
  await until(page, async () => (await api.state())!.run === 0, 1, `${name}: walking`, FRAME_MS);
  await page.keyboard.down('ArrowRight');
  await page.keyboard.down(' ');
  await until(page, async () => (await api.state())!.airborne, 1, `${name}: taking off`, FRAME_MS);
  await until(page, async () => !(await api.state())!.airborne, 3, `${name}: landing`, FRAME_MS);
  await page.keyboard.up(' ');
  await page.keyboard.up('ArrowRight');
  await run(page, 100);
  return (await api.state())!;
}

/** Level 0's gate: the player's own jump falls back from its weir, the spring feet get onto it, and the bionic legs cross its high gap. */
async function sewersLeg(page: Page, api: Api, index: number): Promise<void> {
  const name = "the sewers' gate";
  const xs = [...Array((await api.widths()).sewers).keys()];
  const weir = (await Promise.all(xs.map((x) => api.standing(sewers(x, 12))))).indexOf(true);
  if (weir < WEIR_AT) throw new Error(`${name}: no weir on level 0`);
  const gate = weir - WEIR_AT;
  await fitKit(api, {});
  const short = await atTheWeir(page, api, weir, `${name}, short of the weir`);
  if (short.y !== 15 || short.x > weir - 0.5) throw new Error(`${name}: their own jump landed at ${short.x.toFixed(2)}, ${short.y}`);
  await fitKit(api, { feet: 'spring_feet' });
  const onto = await atTheWeir(page, api, weir, `${name}, onto the weir on the spring feet`);
  if (onto.y !== 12) throw new Error(`${name}: the spring feet landed at ${onto.x.toFixed(2)}, ${onto.y}`);
  await shot(page, index, 'on the weir');
  let from = gate + 2;
  while (from > gate - 6 && (await api.standing(sewers(from - 1, 5)))) from--;
  const across: Jump = { name: "across the gate's high gap on the bionic legs", from: sewers(from, 5), takeOff: gate + 2, land: gate + 7.25, onto: 5, run: true };
  await legsJump(page, api, { legs: 'bionic_legs' }, across, 1, index);
  await fitKit(api, {});
}

const shown = (page: Page, selector: string) =>
  page.evaluate((selector) => {
    const element = document.querySelector<HTMLElement>(selector);
    return element && !element.hidden ? element.textContent : null;
  }, selector);

/** E at a news terminal opens the news, and Esc closes it. */
async function terminalLeg(page: Page, api: Api, at: Place, index: number): Promise<void> {
  const name = `the terminal on ${at.map}`;
  await teleport(page, api, at, name);
  await run(page, 200);
  if (!(await shown(page, '.news-hint'))?.includes('Press E')) throw new Error(`${name}: no hint to press E`);
  await page.keyboard.press('e');
  await run(page, 300);
  await shot(page, index, name);
  if ((await shown(page, 'section.news')) === null) throw new Error(`${name}: E didn't open the news`);
  await page.keyboard.press('Escape');
  await run(page, 200);
  if ((await shown(page, 'section.news')) !== null) throw new Error(`${name}: Esc didn't close the news`);
  if (!near(await api.state(), at)) throw new Error(`${name}: the player moved`);
}

/** E at the café counter opens the chat to whoever is behind it, and Esc closes it. */
async function counterLeg(page: Page, api: Api, counter: Counter, index: number): Promise<void> {
  const name = `the counter on ${counter.map}`;
  await api.move('odalys', { map: counter.map, x: counter.behind, y: counter.y });
  const stand = { map: counter.map, x: counter.x, y: counter.y };
  await teleport(page, api, stand, name);
  await run(page, 500);
  if (!(await shown(page, '.counter-hint'))?.includes('Press E')) throw new Error(`${name}: no hint to press E`);
  await page.keyboard.press('e');
  await run(page, 300);
  await shot(page, index, name);
  const chat = await shown(page, '.dialogue-chat');
  if (!chat?.includes('Odalys')) throw new Error(`${name}: E didn't open the chat to Odalys, only ${chat}`);
  await page.keyboard.press('Escape');
  await run(page, 200);
  if ((await shown(page, '.dialogue-chat')) !== null) throw new Error(`${name}: Esc didn't close the chat`);
  if (!near(await api.state(), stand)) throw new Error(`${name}: the player moved`);
}

/** E beside Lachlan, with nothing else here, opens the chat to him, and Esc closes it. */
async function talkLeg(page: Page, api: Api, index: number): Promise<void> {
  const name = 'talking to Lachlan';
  const at = { map: 'high_street', x: 27, y: 15 };
  await teleport(page, api, at, name);
  await run(page, 500);
  const { talk, prompts, used } = (await api.state())!;
  if (talk !== 'E: talk to Lachlan' || prompts.length || used) {
    throw new Error(`${name}: ${JSON.stringify({ talk, prompts, used })}`);
  }
  await shot(page, index, name);
  await page.keyboard.press('e');
  await run(page, 300);
  const chat = await shown(page, '.dialogue-chat');
  if (!chat?.includes('Lachlan')) throw new Error(`${name}: E didn't open the chat to Lachlan, only ${chat}`);
  await page.keyboard.press('Escape');
  await run(page, 200);
  if ((await shown(page, '.dialogue-chat')) !== null) throw new Error(`${name}: Esc didn't close the chat`);
  if (!near(await api.state(), at)) throw new Error(`${name}: the player moved`);
}

const root = new URL('../..', import.meta.url).pathname;
const server = await createServer({ root, configFile: false, logLevel: 'error', server: { port: 0 } });
await server.listen();
const GL: Record<string, string[]> = {
  darwin: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'],
  linux: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
};
const browser = await chromium.launch({ args: GL[process.platform] ?? [] });
const failures: string[] = [];
try {
  const page = await browser.newPage({ viewport: screens ? { width: 1440, height: 900 } : { width: 320, height: 200 } });
  page.on('pageerror', (error) => failures.push(`page error: ${error.message}`));
  if (!realTime) await page.clock.install();
  const url = server.resolvedUrls!.local[0];
  await page.goto(`${url}?harness=side&still&panel=0&murals=0`);
  if (!realTime) await page.clock.pauseAt(Date.now() + 1000);
  const api = walkApi(page);
  await until(page, async () => !!(await page.evaluate(() => 'sideWalk' in window)) && !!(await api.state()), 60, 'starting');
  const all: [string, (index: number) => Promise<string | void>][] = [
    ...(await legs(api)).map((leg): [string, (index: number) => Promise<string | void>] => [leg.name, (i) => walkLeg(page, api, leg, i)]),
    ['running with Shift', (i) => runLeg(page, api, i)],
    ...JUMPS.map((jump): [string, (index: number) => Promise<string | void>] => [`jumping ${jump.name}`, (i) => jumpLeg(page, api, jump, i)]),
    ["falling off the clock house's roof", (i) => fallLeg(page, api, i)],
    ['through the metro and back', (i) => metroLeg(page, api, i)],
    ['through the dark with the lamp', (i) => lampLeg(page, api, i)],
    [`jumping ${SHORT.name}`, (i) => jumpLeg(page, api, SHORT, i)],
    ['the bionics at the depot', (i) => bionicsLeg(page, api, i)],
    ["the sewers' gate", (i) => sewersLeg(page, api, i)],
    ...(await api.terminals()).map((at): [string, (index: number) => Promise<string | void>] => [
      `E at the terminal on ${at.map}`,
      (i) => terminalLeg(page, api, at, i),
    ]),
    ...(await api.counters()).map((counter): [string, (index: number) => Promise<string | void>] => [
      `E at the counter on ${counter.map}`,
      (i) => counterLeg(page, api, counter, i),
    ]),
    ['E beside a resident', (i) => talkLeg(page, api, i)],
  ];
  const started = Date.now();
  for (const [i, [name, walk]] of all.entries()) {
    try {
      const note = await walk(i);
      console.log(`ok   ${name}${note ? `: ${note}` : ''}`);
    } catch (error) {
      failures.push((error as Error).message);
      console.log(`FAIL ${(error as Error).message}`);
    }
  }
  console.log(`${all.length - failures.length} of ${all.length} legs in ${((Date.now() - started) / 1000).toFixed(0)} s`);
} finally {
  await browser.close();
  await server.close();
}
if (failures.length) {
  console.log(failures.join('\n'));
  process.exitCode = 1;
}
