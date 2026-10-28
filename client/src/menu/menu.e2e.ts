// P30's menus in Chromium against `simile worlds serve` on the fake LLM, in worlds of its own.
import { chromium, type Page } from 'playwright';
import { createServer } from 'vite';

declare const process: {
  argv: string[];
  platform: string;
  env: Record<string, string | undefined>;
  exitCode?: number;
  kill(pid: number, signal: string): void;
};

type Readable = { on(event: 'data', listener: (chunk: { toString(): string }) => void): void };
type Child = { pid?: number; exitCode: number | null; stdout: Readable; stderr: Readable };
type ChildProcess = {
  spawn(
    command: string,
    args: string[],
    options: { cwd: string; detached?: boolean; env: Record<string, string | undefined> },
  ): Child;
};
type Fs = {
  mkdtempSync(prefix: string): string;
  mkdirSync(path: string, options: { recursive: true }): void;
  rmSync(path: string, options: { recursive: true; force: true }): void;
};
type Net = {
  createServer(): {
    listen(port: number, ready: () => void): { address(): { port: number }; close(): void };
  };
};
const node = <T>(name: string) => import(name) as Promise<T>;
const [{ spawn }, fs, { tmpdir }, net] = await Promise.all([
  node<ChildProcess>('node:child_process'),
  node<Fs>('node:fs'),
  node<{ tmpdir(): string }>('node:os'),
  node<Net>('node:net'),
]);

type Listing = { current: { id: string | null; name: string }; worlds: { id: string; name: string }[] };
type View = { positionOf(id: string): { map: string; x: number } | undefined };
type Probed = { menuProbe: () => View };

const args = process.argv.slice(2);
const option = (name: string) => (args.includes(name) ? args[args.indexOf(name) + 1] : undefined);
const screens = option('--screens');
const SECONDS = 120;
const root = new URL('../..', import.meta.url).pathname;
const serverDir = new URL('../../../server', import.meta.url).pathname;

async function freePort(): Promise<number> {
  return new Promise((resolve) => {
    const listening = net.createServer().listen(0, () => {
      const { port } = listening.address();
      listening.close();
      resolve(port);
    });
  });
}

async function until<T>(check: () => Promise<T | undefined | false>, what: string): Promise<T> {
  for (let waited = 0; waited < SECONDS * 1000; waited += 250) {
    const found = await check().catch(() => undefined);
    if (found) return found;
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  throw new Error(`${what}: not within ${SECONDS} s`);
}

const port = await freePort();
const api = `http://127.0.0.1:${port}`;
const listing = (): Promise<Listing> => fetch(`${api}/api/worlds`).then((r) => r.json());
const running = (id: string) => until(async () => (await listing()).current.id === id, `the server on ${id}`);

const vite = await createServer({
  root,
  configFile: false,
  logLevel: 'silent',
  server: { port: 0, proxy: { '/api': api, '/ws': { target: api, ws: true } } },
});
await vite.listen();
const url = vite.resolvedUrls!.local[0];

const scratch = fs.mkdtempSync(`${tmpdir()}/simile-menu-`);
fs.mkdirSync(`${scratch}/start`, { recursive: true });
const supervisor = spawn('uv', ['run', 'simile', 'worlds', 'serve', '--port', String(port)], {
  cwd: serverDir,
  detached: true,
  env: {
    ...process.env,
    SIMILE_WORLDS: `${scratch}/worlds`,
    SIMILE_LIBRARY: `${scratch}/library`,
    SIMILE_DB: `${scratch}/start/simile.db`,
    SIMILE_LLM: 'fake',
    SIMILE_NEWS: '0',
    SIMILE_ORIGINS: new URL(url).origin,
  },
});
const log: string[] = [];
for (const stream of [supervisor.stdout, supervisor.stderr])
  stream.on('data', (chunk) => log.push(chunk.toString()));

const GL: Record<string, string[]> = {
  darwin: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'],
  linux: ['--use-angle=swiftshader', '--enable-unsafe-swiftshader'],
};
const browser = await chromium.launch({ args: GL[process.platform] ?? [] });
const failures: string[] = [];
let shots = 0;

async function shot(page: Page, what: string): Promise<void> {
  if (screens)
    await page.screenshot({ path: `${screens}/${String(++shots).padStart(2, '0')}-${what}.png` });
}

/** Waits for the reload into the game, and for the side scene to draw the player. */
async function inGame(page: Page): Promise<void> {
  await page.waitForURL(/\?play$/, { timeout: SECONDS * 1000 });
  await until(
    () =>
      page.evaluate(async (module) => {
        const { worldView, trackedWorld, PLAYER_ID } = await import(module);
        (window as unknown as Probed).menuProbe = worldView;
        return worldView() !== trackedWorld && !!worldView().positionOf(PLAYER_ID);
      }, '/src/ui/world-view.ts'),
    'the side scene drawing the player',
  );
}

const playerAt = (page: Page) =>
  page.evaluate(() => (window as unknown as Probed).menuProbe().positionOf('player'));

try {
  if (screens) fs.mkdirSync(screens, { recursive: true });
  await until(() => listing(), 'the server starting');
  const made = await fetch(`${api}/api/worlds`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ count: 4, name: 'Ash Lane', open: true }),
  }).then((r) => r.json() as Promise<{ id: string }>);
  const first = made.id;
  await running(first);
  console.log(`ok   started on the first world, ${first}`);

  const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  page.on('pageerror', (error) => failures.push(`page error: ${error.message}`));
  await page.goto(url);
  await page.getByRole('button', { name: /^Continue.*Ash Lane/ }).waitFor();
  await shot(page, 'title');

  await page.getByRole('button', { name: /^New game/ }).click();
  await page.getByRole('button', { name: 'Start' }).waitFor();
  const name = await page.getByLabel('Name').inputValue();
  await shot(page, 'new-game');
  await page.getByRole('button', { name: 'Start' }).click();
  await page.getByRole('heading', { name: new RegExp(`^(Making|Opening) ${name}`) }).waitFor();
  await shot(page, 'opening');
  await inGame(page);
  const second = (await listing()).current;
  if (second.name !== name || second.id === first) throw new Error(`opened ${JSON.stringify(second)}`);
  console.log(`ok   made ${name} from the menu and went into it`);

  const before = await playerAt(page);
  await page.keyboard.down('ArrowRight');
  await until(async () => ((await playerAt(page))?.x ?? 0) > before!.x + 1, 'walking right');
  await page.keyboard.up('ArrowRight');
  await shot(page, 'playing');
  console.log('ok   walked in it');

  await page.keyboard.press('Escape');
  await page.getByRole('dialog', { name: 'Pause menu' }).waitFor();
  await shot(page, 'pause');
  await page.getByRole('button', { name: 'Controls' }).click();
  await shot(page, 'pause-controls');
  const held = await playerAt(page);
  await page.keyboard.down('ArrowLeft');
  await page.waitForTimeout(500);
  await page.keyboard.up('ArrowLeft');
  if ((await playerAt(page))?.x !== held?.x) throw new Error('walked with the pause menu open');
  await page.getByRole('button', { name: 'Exit to menu' }).click();
  await page.getByRole('button', { name: /^Continue/ }).waitFor();
  console.log('ok   Esc, then Exit to menu');

  await page.getByRole('button', { name: /^Load game/ }).click();
  await page.locator('.menu-world').first().waitFor();
  await shot(page, 'load-game');
  await page.locator('.menu-world', { hasText: 'Ash Lane' }).locator('.menu-world-open').click();
  await inGame(page);
  await running(first);
  await shot(page, 'back-in-the-first');
  console.log('ok   loaded the first world back');

  await page.keyboard.press('Escape');
  await page.getByRole('button', { name: 'Exit to menu' }).click();
  await page.getByRole('button', { name: /^Load game/ }).click();
  const made2 = page.locator('.menu-world', { hasText: name });
  await made2.getByRole('button', { name: 'Rename' }).click();
  await page.getByLabel('Name').fill(`${name} Two`);
  await page.getByLabel('Name').press('Enter');
  const renamed = page.locator('.menu-world', { hasText: `${name} Two` });
  await renamed.waitFor();
  await renamed.getByRole('button', { name: 'Delete' }).click();
  await shot(page, 'delete-confirm');
  await page.locator('.menu-world-confirm').getByRole('button', { name: 'Delete' }).click();
  await renamed.waitFor({ state: 'detached' });
  if ((await listing()).worlds.some((world) => world.id === second.id))
    throw new Error(`${second.id} is still listed`);
  console.log('ok   renamed and deleted the second world');
} catch (error) {
  failures.push((error as Error).message);
  console.log(`FAIL ${(error as Error).message}`);
  const page = browser.contexts()[0]?.pages()[0];
  if (page) await shot(page, 'failed');
} finally {
  await browser.close();
  await vite.close();
  process.kill(-supervisor.pid!, 'SIGTERM');
  for (let waited = 0; supervisor.exitCode === null && waited < 10_000; waited += 100)
    await new Promise((resolve) => setTimeout(resolve, 100));
  if (supervisor.exitCode === null) process.kill(-supervisor.pid!, 'SIGKILL');
  fs.rmSync(scratch, { recursive: true, force: true });
}
if (failures.length) {
  console.log(log.join('').split('\n').slice(-40).join('\n'));
  console.log(failures.join('\n'));
  process.exitCode = 1;
}
