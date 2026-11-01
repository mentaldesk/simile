// Stage 2's loop in Chromium, by the keys, against the real server on the fake LLM: server/simile/loop/README.md.
import { chromium, type Browser, type Page } from 'playwright';
import { createServer } from 'vite';

declare const process: { argv: string[]; platform: string; exitCode?: number; kill(pid: number, signal: string): void };

type Readable = { on(event: 'data', listener: (chunk: { toString(): string }) => void): void };
type Child = { pid?: number; exitCode: number | null; stdout: Readable; stderr: Readable; once(event: 'exit', listener: (code: number | null) => void): void };
type ChildProcess = { spawn(command: string, args: string[], options: { cwd: string; detached?: boolean }): Child };
type Fs = {
  readFileSync(path: string, encoding: 'utf8'): string;
  mkdtempSync(prefix: string): string;
  mkdirSync(path: string, options: { recursive: true }): void;
  rmSync(path: string, options: { recursive: true; force: true }): void;
};
type Net = { createServer(): { listen(port: number, ready: () => void): { address(): { port: number }; close(): void } } };
const node = <T>(name: string) => import(name) as Promise<T>;
const [{ spawn }, fs, { tmpdir }, net] = await Promise.all([
  node<ChildProcess>('node:child_process'),
  node<Fs>('node:fs'),
  node<{ tmpdir(): string }>('node:os'),
  node<Net>('node:net'),
]);

type Place = { map: string; x: number; y: number };
type Body = Record<string, string>;
type Seen = Place & { money: number; body: Body };
/** What `simile loop play --saves` writes beside each beat's world. */
type Saved = {
  at: Place;
  money: number;
  lift_log?: string;
  hatch_log?: string;
  hatch?: { x: number; y: number };
  gap?: { from: number; to: number; row: number };
};
type Probe = { view(): { positionOf(id: string): Place | undefined }; playerState: { latest?: { player: { money: number; body: Body } } } };
type Probed = { loopProbe: Probe };
type Beat = (page: Page, saved: Saved, shot: (name: string) => Promise<void>) => Promise<void>;
type Hold = 'ArrowUp' | 'ArrowDown';

const args = process.argv.slice(2);
const option = (name: string) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);
const screens = option('--screens');
const FRAME_MS = 1000 / 60;
const REACH = { cell: 0.45 };
const SECONDS_TO_ARRIVE = 12;
/** Real seconds the server has to answer something: a sale, a fitting, a reply. */
const SERVER_SECONDS = 30;
/** Real seconds the client has to load, the first time Vite builds it. */
const LOAD_SECONDS = 120;
const root = new URL('../..', import.meta.url).pathname;
const serverDir = new URL('../../../server', import.meta.url).pathname;

const metro = (x: number, y: number): Place => ({ map: 'metro', x, y });
const CLINIC: Place = { map: 'clinic_floor_0', x: 1, y: 2 };
const SEWERS: Place = { map: 'sewers', x: 2, y: 15 };
/** The walk's jump onto the metro's high ledge on the bionic legs and spring feet, landing on its secret's cell. */
const LEDGE = { from: 96, takeOff: 104.4, land: 106, onto: 12 };
/** Cells of run-up before the gate's gap, and how far short of its edge the run jump takes off. */
const GATE = { runUp: 6, early: 0.3 };

async function run(page: Page, ms: number): Promise<void> {
  await page.clock.runFor(Math.ceil(ms / FRAME_MS) * FRAME_MS);
}

/** Steps the page's clock, letting the real server's messages in between. */
async function until(page: Page, check: () => Promise<boolean>, seconds: number, what: string, step = 100): Promise<void> {
  for (let waited = 0; waited < seconds * 1000; waited += step) {
    if (await check()) return;
    await run(page, step);
    await page.waitForTimeout(10);
  }
  throw new Error(`${what}: not within ${seconds} s`);
}

/** Real time for the server or the page to load, with the page's clock kept up. */
async function awaitServer(page: Page, check: () => Promise<boolean>, what: string, seconds = SERVER_SECONDS): Promise<void> {
  for (let waited = 0; waited < seconds * 1000; waited += 100) {
    if (await check()) return;
    await page.waitForTimeout(90);
    await run(page, 100);
  }
  throw new Error(`${what}: not within ${seconds} real seconds`);
}

const seen = (page: Page) =>
  page.evaluate((): Seen | undefined => {
    const probe = (window as unknown as Probed).loopProbe;
    const at = probe.view().positionOf('player');
    const player = probe.playerState.latest?.player;
    return at && player && { map: at.map, x: at.x, y: at.y, money: player.money, body: player.body };
  });

const shown = (page: Page, selector: string) =>
  page.evaluate((selector) => {
    const element = document.querySelector<HTMLElement>(selector);
    return element && !element.hidden ? element.textContent : null;
  }, selector);

const near = (at: Seen | undefined, place: Place, by = 0.01) =>
  !!at && at.map === place.map && Math.abs(at.x - place.x) <= by && Math.abs(at.y - place.y) <= by;

async function walkTo(page: Page, x: number, reach: number, what: string): Promise<void> {
  const from = (await seen(page))!.x;
  if (Math.abs(from - x) <= reach) return;
  const key = x > from ? 'ArrowRight' : 'ArrowLeft';
  await page.keyboard.down(key);
  await until(page, async () => Math.abs((await seen(page))!.x - x) <= reach, 40, `${what}: walking to ${x}`, FRAME_MS);
  await page.keyboard.up(key);
  await run(page, 200);
}

async function take(page: Page, key: 'e' | Hold, arrive: Place, what: string): Promise<void> {
  if (key === 'e') await page.keyboard.press('e');
  else await page.keyboard.down(key);
  await until(page, async () => near(await seen(page), arrive), SECONDS_TO_ARRIVE, `${what}: arriving at ${JSON.stringify(arrive)}`);
  if (key !== 'e') await page.keyboard.up(key);
  await run(page, 300);
}

/** Off the door's cell, where E takes the door, then E. */
async function openClinic(page: Page): Promise<void> {
  await walkTo(page, CLINIC.x + 2, REACH.cell, 'into the clinic');
  await page.keyboard.press('e');
  await until(page, async () => (await shown(page, 'section.clinic')) !== null, 3, 'E opening the clinic');
}

/** Chooses the clinic's row named `label` with the arrows, in its column, and Enter twice, since it can't be undone. */
async function deal(page: Page, label: string, done: (at: Seen) => boolean): Promise<void> {
  const rows = () =>
    page.$$eval('section.clinic li', (items) =>
      items.map((item) => [item.querySelector('.clinic-name')?.textContent ?? '', item.classList.contains('clinic-selected'), !!item.closest('.clinic-yours')] as const),
    );
  const index = (await rows()).findIndex(([text]) => text === label);
  if (index === -1) throw new Error(`the clinic offers no ${label}: ${JSON.stringify(await rows())}`);
  await page.keyboard.press((await rows())[index][2] ? 'ArrowLeft' : 'ArrowRight');
  await run(page, 50);
  for (let tries = 0; !(await rows())[index][1]; tries++) {
    if (tries > 30) throw new Error(`couldn't choose ${label}`);
    await page.keyboard.press('ArrowDown');
    await run(page, 50);
  }
  await page.keyboard.press('Enter');
  await run(page, 50);
  await page.keyboard.press('Enter');
  await awaitServer(page, async () => done((await seen(page))!), label);
}

/** Along to `takeOff` and a jump with Space held until they land, walking or with Shift running. */
async function jump(page: Page, takeOff: number, row: number, running: boolean, what: string): Promise<Seen> {
  if (running) await page.keyboard.press('Shift');
  await run(page, 100);
  await page.keyboard.down('ArrowRight');
  await until(page, async () => (await seen(page))!.x >= takeOff, 5, `${what}: the run-up`, FRAME_MS);
  await page.keyboard.down(' ');
  await until(page, async () => (await seen(page))!.y < row - 0.1, 1, `${what}: taking off`, FRAME_MS);
  let last = NaN;
  const landed = async () => {
    const { y } = (await seen(page))!;
    const still = Number.isInteger(y) && y === last;
    last = y;
    return still;
  };
  await until(page, landed, 3, `${what}: landing`, FRAME_MS);
  await page.keyboard.up(' ');
  await page.keyboard.up('ArrowRight');
  if (running) await page.keyboard.press('Shift');
  await run(page, 300);
  return (await seen(page))!;
}

async function jumpToTheLedge(page: Page): Promise<void> {
  await walkTo(page, LEDGE.from, REACH.cell, 'to the run-up');
  const at = await jump(page, LEDGE.takeOff, 15, false, 'onto the ledge');
  if (at.y !== LEDGE.onto || at.x < LEDGE.land) throw new Error(`landed at ${at.x.toFixed(2)}, ${at.y}, not on the ledge`);
}

async function leaveClinic(page: Page): Promise<void> {
  await walkTo(page, CLINIC.x, REACH.cell, "to the clinic's door");
  await take(page, 'e', metro(89, 15), 'out of the clinic');
}

/** E at a jack with the datajack opens the journal on what it held. */
async function jack(page: Page, text: string, what: string): Promise<void> {
  await page.keyboard.press('e');
  await awaitServer(page, async () => !!(await shown(page, 'section.journal'))?.includes(text), `the journal opening on the ${what}`);
}

/** Into the clinic from outside it, and its deal starting `label`. */
async function fitted(page: Page, label: string, done: (at: Seen) => boolean): Promise<void> {
  await walkTo(page, 89, REACH.cell, 'to the clinic');
  await take(page, 'e', CLINIC, 'into the clinic');
  await openClinic(page);
  await deal(page, label, done);
}

const kidney: Beat = async (page, saved, shot) => {
  await walkTo(page, 89, REACH.cell, 'to the clinic');
  await take(page, 'e', CLINIC, 'into the clinic');
  await openClinic(page);
  await shot('the clinic');
  await deal(page, 'A kidney', (at) => at.money === saved.money + 100 && at.body.left_kidney === 'sold');
  await shot('the kidney sold');
};

const cell: Beat = async (page, _saved, shot) => {
  await fitted(page, 'Power cell', (at) => at.body.stomach === 'power_cell');
  await shot('the power cell fitted');
};

const datajack: Beat = async (page, saved, shot) => {
  await fitted(page, 'Datajack', (at) => at.body.vertebra === 'datajack');
  await page.keyboard.press('Escape');
  await leaveClinic(page);
  await walkTo(page, 104, REACH.cell, 'to the dead terminal');
  await jack(page, saved.lift_log!.slice(0, 40), 'dead terminal');
  await shot('the lift log');
  await page.keyboard.press('Escape');
  await walkTo(page, 100, REACH.cell, 'to the lift');
  await take(page, 'e', SEWERS, 'down the lift');
  await shot('the sewers');
  await take(page, 'e', metro(100, 15), 'up the lift');
};

const legs: Beat = async (page, _saved, shot) => {
  await fitted(page, 'Bionic legs', (at) => at.body.legs === 'bionic_legs');
  await shot('the legs fitted');
};

const gate: Beat = async (page, saved, shot) => {
  const gap = saved.gap!;
  await walkTo(page, gap.from - GATE.runUp, REACH.cell, "to the gate's run-up");
  await shot("the gate's gap");
  const at = await jump(page, gap.from + 0.5 - GATE.early, gap.row, true, "over the gate's gap");
  if (at.y !== gap.row || at.x < gap.to - 0.5) throw new Error(`landed at ${at.x.toFixed(2)}, ${at.y}, not past the gap`);
  await shot('over the gate');
};

const hatch: Beat = async (page, saved, shot) => {
  await walkTo(page, saved.hatch!.x, REACH.cell, 'to the hatch');
  await shot('at the hatch');
  await jack(page, saved.hatch_log!.slice(0, 40), 'maintenance hatch');
  await shot('the hatch log');
};

const feet: Beat = async (page, _saved, shot) => {
  await fitted(page, 'Spring feet', (at) => at.body.feet === 'spring_feet');
  await shot('the feet fitted');
  await page.keyboard.press('Escape');
  await leaveClinic(page);
  await jumpToTheLedge(page);
  await walkTo(page, LEDGE.land, 0.3, "to the secret's cell");
  const money = (await seen(page))!.money;
  await page.keyboard.press('e');
  await awaitServer(page, async () => (await seen(page))!.money === money + 60, 'picking up the secret');
  await shot('the secret on the high ledge');
};

const BEATS: [string, Beat][] = [
  ['kidney', kidney],
  ['cell', cell],
  ['datajack', datajack],
  ['legs', legs],
  ['gate', gate],
  ['hatch', hatch],
  ['feet', feet],
];

function exited(child: Child, what: string): Promise<void> {
  return new Promise((resolve, reject) =>
    child.once('exit', (code) => (code === 0 ? resolve() : reject(new Error(`${what} exited with ${code}`)))),
  );
}

function echo(child: Child, prefix = ''): void {
  for (const stream of [child.stdout, child.stderr]) stream.on('data', (chunk) => console.log(prefix + chunk.toString().trimEnd()));
}

async function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const server = net.createServer();
    const listening = server.listen(0, () => {
      const { port } = listening.address();
      listening.close();
      resolve(port);
    });
  });
}

/** `simile loop serve` on a copy of the beat's world, until stopped. */
async function serve(world: string, at: Place, port: number, origin: string): Promise<() => Promise<void>> {
  const args = ['run', 'simile', 'loop', 'serve', world, '--at', `${at.map}:${at.x}:${at.y}`, '--port', String(port), '--origin', origin];
  const child = spawn('uv', args, { cwd: serverDir, detached: true });
  const errors: string[] = [];
  child.stdout.on('data', () => {});
  child.stderr.on('data', (chunk) => errors.push(chunk.toString()));
  for (let waited = 0; ; waited += 200) {
    const healthy = await fetch(`http://127.0.0.1:${port}/api/health`).then((response) => response.ok, () => false);
    if (healthy) break;
    if (child.exitCode !== null || waited > 60_000) throw new Error(`the server didn't start: ${errors.join('')}`);
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return async () => {
    process.kill(child.pid!, 'SIGTERM');
    for (let waited = 0; child.exitCode === null && waited < 10_000; waited += 100) await new Promise((resolve) => setTimeout(resolve, 100));
    if (child.exitCode === null) process.kill(-child.pid!, 'SIGKILL');
  };
}

/** The real client, started on the snapshot's player, with the modules this script reads them through. */
async function open(browser: Browser, url: string, failures: string[]): Promise<Page> {
  const page = await browser.newPage({ viewport: screens ? { width: 1440, height: 900 } : { width: 640, height: 400 } });
  page.on('pageerror', (error) => failures.push(`page error: ${error.message}`));
  let snapshot = () => {};
  const arrived = new Promise<void>((resolve) => (snapshot = resolve));
  page.on('websocket', (socket) => socket.on('framereceived', ({ payload }) => String(payload).startsWith('{"type":"snapshot"') && snapshot()));
  await page.route(/\/src\/side\/content\.ts/, async (route) => {
    await arrived;
    await route.continue();
  });
  const start = Date.now();
  await page.clock.install({ time: start });
  await page.clock.pauseAt(start + 1000);
  await page.goto(`${url}?play`);
  await page.evaluate(
    async ([view, net]) => {
      const [{ worldView }, { playerState }] = await Promise.all([import(view), import(net)]);
      (window as unknown as Probed).loopProbe = { view: worldView, playerState };
    },
    ['/src/ui/world-view.ts', '/src/net/index.ts'],
  );
  return page;
}

const kept = option('--saves');
const saves = kept ?? fs.mkdtempSync(`${tmpdir()}/simile-loop-`);
if (!kept) {
  console.log(`Playing the loop in the sim, saving its beats to ${saves}`);
  const sim = spawn('uv', ['run', 'simile', 'loop', 'play', '--saves', saves], { cwd: serverDir });
  echo(sim, 'sim  ');
  await exited(sim, 'simile loop play');
}
if (screens) fs.mkdirSync(screens, { recursive: true });
const port = await freePort();
const target = `http://127.0.0.1:${port}`;
const vite = await createServer({
  root,
  configFile: false,
  logLevel: 'error',
  server: { port: 0, proxy: { '/api': target, '/ws': { target, ws: true } } },
});
await vite.listen();
const url = vite.resolvedUrls!.local[0];
const GL: Record<string, string[]> = {
  darwin: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'],
  linux: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
};
const browser = await chromium.launch({ args: GL[process.platform] ?? [] });
const failures: string[] = [];
let shots = 0;
try {
  for (const [name, beat] of BEATS.filter(([name]) => !option('--beat') || option('--beat') === name)) {
    const saved = JSON.parse(fs.readFileSync(`${saves}/${name}.json`, 'utf8')) as Saved;
    const started = Date.now();
    const stop = await serve(`${saves}/${name}.db`, saved.at, port, new URL(url).origin);
    try {
      const page = await open(browser, url, failures);
      const shot = async (what: string) => {
        if (screens) await page.screenshot({ path: `${screens}/${String(++shots).padStart(2, '0')}-${what.replaceAll(/\W+/g, '-')}.jpg`, type: 'jpeg', quality: 85 });
      };
      try {
        await awaitServer(page, async () => near(await seen(page), saved.at), `starting at ${JSON.stringify(saved.at)}`, LOAD_SECONDS);
        await run(page, 1500);
        await beat(page, saved, shot);
        console.log(`ok   ${name} in ${((Date.now() - started) / 1000).toFixed(0)} s`);
      } catch (error) {
        await shot(`${name} failed`);
        throw error;
      } finally {
        await page.close();
      }
    } catch (error) {
      failures.push(`${name}: ${(error as Error).message}`);
      console.log(`FAIL ${name}: ${(error as Error).message}`);
    } finally {
      await stop();
    }
  }
} finally {
  await browser.close();
  await vite.close();
  if (!kept) fs.rmSync(saves, { recursive: true, force: true });
}
if (failures.length) {
  console.log(failures.join('\n'));
  process.exitCode = 1;
}
