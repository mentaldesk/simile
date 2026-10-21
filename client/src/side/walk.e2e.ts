// The player's walk through the side view in Chromium, by the keys (#325): into every building, up and down every
// flight, ladder and lift, and out of every exit. It serves the client itself and drives the `?harness=side` scene.
// Run `npx playwright install chromium` once, then `node src/side/walk.e2e.ts [--screens <dir>] [--real-time]`.
import { chromium, type Page } from 'playwright';
import { createServer } from 'vite';

declare const process: { argv: string[]; platform: string; exitCode?: number };

type Cell = { x: number; y: number };
type Place = Cell & { map: string };
type Link = Place & { id: string; kind: 'door' | 'stairs' | 'ladder' | 'lift'; side: 'inside' | 'outside'; to: Place };
type Run = { map: string; kind: string; foot: Cell; head: Cell };
type State = Place & { climbing: string | null; prompts: string[] };
type SideWalk = {
  state(): State | undefined;
  links(): Link[];
  runs(): Run[];
  widths(): Record<string, number>;
  standing(map: string, x: number, y: number): boolean;
  teleport(to: Place): void;
};
type Paged = { sideWalk: SideWalk };
type Hold = 'ArrowUp' | 'ArrowDown';
/** Walk from `start` to within `reach` of `x` on its row, press E or not, hold up or down or not, and arrive at
 * `arrive`. */
type Leg = { name: string; start: Place; x: number; reach: number; e: boolean; hold?: Hold; arrive: Place };

const args = process.argv.slice(2);
const option = (name: string) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);
const screens = option('--screens');
const realTime = args.includes('--real-time');
const FRAME_MS = 1000 / 60;
const SECONDS_TO_ARRIVE = 12;
/** On the cell of a door or a lift; near the far edge of the tile beside a flight's or a ladder's end. */
const REACH = { cell: 0.45, edge: 1.4 };

const walkApi = (page: Page) => ({
  state: () => page.evaluate(() => (window as unknown as Paged).sideWalk.state()),
  links: () => page.evaluate(() => (window as unknown as Paged).sideWalk.links()),
  runs: () => page.evaluate(() => (window as unknown as Paged).sideWalk.runs()),
  widths: () => page.evaluate(() => (window as unknown as Paged).sideWalk.widths()),
  standing: (place: Place) =>
    page.evaluate(({ map, x, y }) => (window as unknown as Paged).sideWalk.standing(map, x, y), place),
  teleport: (to: Place) => page.evaluate((to) => (window as unknown as Paged).sideWalk.teleport(to), to),
});

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

/** A standing cell two tiles from `end` along its row, towards the middle of the map, to walk from. */
async function startFor(api: ReturnType<typeof walkApi>, end: Place, width: number): Promise<Place> {
  const towards = end.x < width / 2 ? 1 : -1;
  for (const step of [2, -2, 1, -1]) {
    const x = end.x + towards * step;
    if (await api.standing({ map: end.map, x, y: end.y })) return { map: end.map, x, y: end.y };
  }
  return end;
}

/** Doors in on up and out on E; stairs and ladders up from their foot on up alone, and down from their top on E
 * then down; lifts on E. */
async function legs(api: ReturnType<typeof walkApi>): Promise<Leg[]> {
  const [links, widths] = [await api.links(), await api.widths()];
  const far = (link: Link) => links.find(({ map, x, y }) => map === link.to.map && x === link.to.x && y === link.to.y)!;
  const found: Leg[] = [];
  for (const link of links) {
    const there = far(link);
    const [inside, goingIn] = [link.map.includes('_floor_'), there.map.includes('_floor_')];
    const arrive = { map: there.map, x: there.x, y: there.y };
    const start = await startFor(api, link, widths[link.map]);
    const leg = { start, x: link.x, arrive, reach: link.kind === 'stairs' || link.kind === 'ladder' ? REACH.edge : REACH.cell };
    if (link.kind === 'door' && !inside) {
      found.push({ ...leg, name: goingIn ? `into ${there.map}` : `${link.map} to ${there.map}`, e: false, hold: 'ArrowUp' });
    } else if (link.kind === 'door') found.push({ ...leg, name: `out of ${link.map}`, e: true });
    else if (link.kind === 'lift') found.push({ ...leg, name: `${link.id} from ${link.map}`, e: true });
    else {
      const up = link.side === 'outside';
      found.push({ ...leg, name: `${link.id} ${up ? 'up' : 'down'} from ${link.map}`, e: !up, hold: up ? 'ArrowUp' : 'ArrowDown' });
    }
  }
  for (const run of await api.runs()) {
    for (const [from, to, up] of [
      [run.foot, run.head, true],
      [run.head, run.foot, false],
    ] as const) {
      const start = await startFor(api, { map: run.map, ...from }, widths[run.map]);
      const name = `${run.kind} on ${run.map} ${up ? 'up' : 'down'} from ${from.x}, ${from.y}`;
      const arrive = { map: run.map, ...to };
      found.push({ name, start, x: from.x, reach: REACH.edge, e: !up, hold: up ? 'ArrowUp' : 'ArrowDown', arrive });
    }
  }
  return found;
}

async function walkLeg(page: Page, api: ReturnType<typeof walkApi>, leg: Leg, index: number): Promise<void> {
  for (let tries = 1; ; tries++) {
    await api.teleport(leg.start);
    try {
      await until(page, async () => near(await api.state(), leg.start), 10, `${leg.name}: getting to the start`);
      break;
    } catch (error) {
      if (tries === 3) throw error;
    }
  }
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
  const { prompts, x } = (await api.state())!;
  if (leg.reach === REACH.edge && Math.abs(x - leg.x) < 1.3) {
    throw new Error(`${leg.name}: stopped ${Math.abs(x - leg.x).toFixed(2)} from ${leg.x}, not at the edge of its reach`);
  }
  const key = leg.e ? 'E' : leg.hold === 'ArrowUp' ? '↑' : '↓';
  if (!prompts.some((prompt) => prompt.split(':')[0].includes(key))) {
    throw new Error(`${leg.name}: no prompt for ${key} at ${leg.x}, only ${JSON.stringify(prompts)}`);
  }
  if (screens) {
    const path = `${screens}/${String(index).padStart(3, '0')}-${leg.name.replaceAll(/\W+/g, '-')}.jpg`;
    await page.screenshot({ path, type: 'jpeg', quality: 80 });
  }
  if (leg.e) {
    await page.keyboard.press('e');
    await run(page, 100);
  }
  if (leg.hold) await page.keyboard.down(leg.hold);
  const arrive = `${leg.name}: arriving at ${JSON.stringify(leg.arrive)}`;
  await until(page, async () => near(await api.state(), leg.arrive), SECONDS_TO_ARRIVE, arrive);
  if (leg.hold) await page.keyboard.up(leg.hold);
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
  const all = await legs(api);
  const started = Date.now();
  for (const [i, leg] of all.entries()) {
    try {
      await walkLeg(page, api, leg, i);
      console.log(`ok   ${leg.name}`);
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
