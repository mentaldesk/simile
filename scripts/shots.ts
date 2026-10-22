// #357's previews: the player with each combination of bionics in the real client's side view, standing,
// walking and jumping. node shots.ts <client dir> <out dir>
import { chromium, type Page } from 'playwright';
import { createServer } from 'vite';

declare const process: { argv: string[] };

const [root, out] = process.argv.slice(2);
const FRAME_MS = 1000 / 60;
const AT = { map: process.argv[4] ?? 'high_street', x: Number(process.argv[5] ?? 60), y: 15 };
const COMBINATIONS: string[][] = [
  [],
  ['hydraulic_legs'],
  ['datajack'],
  ['infrared_eye'],
  ['hydraulic_legs', 'datajack'],
  ['hydraulic_legs', 'infrared_eye'],
  ['datajack', 'infrared_eye'],
  ['hydraulic_legs', 'datajack', 'infrared_eye'],
];
const NAMES: Record<string, string> = { hydraulic_legs: 'legs', datajack: 'datajack', infrared_eye: 'eye' };

const body = (fitted: string[]) => ({
  legs: fitted.includes('hydraulic_legs') ? 'hydraulic_legs' : 'present',
  vertebra: fitted.includes('datajack') ? 'datajack' : 'present',
  left_eye: 'present',
  right_eye: fitted.includes('infrared_eye') ? 'infrared_eye' : 'present',
  left_kidney: 'sold',
  right_kidney: 'present',
});

async function run(page: Page, ms: number): Promise<void> {
  await page.clock.runFor(Math.ceil(ms / FRAME_MS) * FRAME_MS);
  await page.waitForTimeout(30);
}

async function fit(page: Page, fitted: string[]): Promise<void> {
  const player = { money: 0, items: [], carry_limit: 10, hunger: 0, body: body(fitted) };
  await page.evaluate(async (message) => {
    const { server } = await import('/src/net/index.ts');
    server.dispatch(JSON.stringify(message));
  }, { type: 'player_state', player });
  for (let i = 0; i < 20; i++) {
    await run(page, 100);
    await page.waitForTimeout(50);
  }
}

/** The player's box on screen, from the scene's camera and the player's position. */
async function box(page: Page) {
  return page.evaluate(() => {
    const scene = (window as any).sideScene;
    const camera = scene.cameras.main;
    const figure = scene.figures.get('player');
    const doll = figure.doll;
    const bounds = doll.getBounds();
    const zoom = camera.zoom;
    const canvas = scene.game.canvas.getBoundingClientRect();
    const ratio = canvas.width / scene.game.canvas.width;
    const x = (bounds.x - camera.worldView.x) * zoom * ratio + canvas.left;
    const y = (bounds.y - camera.worldView.y) * zoom * ratio + canvas.top;
    return { x, y, width: bounds.width * zoom * ratio, height: bounds.height * zoom * ratio };
  });
}

async function shot(page: Page, name: string): Promise<void> {
  const b = await box(page);
  const pad = 40;
  const clip = { x: b.x - pad, y: b.y - pad, width: b.width + 2 * pad, height: b.height + 2 * pad };
  await page.screenshot({ path: `${out}/${name}.png`, clip });
}

const server = await createServer({ root, configFile: false, logLevel: 'error', server: { port: 0 } });
await server.listen();
const browser = await chromium.launch({ args: ['--use-angle=metal', '--enable-gpu', '--ignore-gpu-blocklist'] });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  page.on('pageerror', (error) => console.log(`page error: ${error.message}`));
  await page.clock.install();
  const url = server.resolvedUrls!.local[0];
  await page.goto(`${url}?harness=side&still&panel=0&murals=0&at=${AT.map}:${AT.x}:${AT.y}&hour=11`);
  await page.clock.pauseAt(Date.now() + 1000);
  for (let i = 0; i < 100 && !(await page.evaluate(() => (window as any).sideWalk?.state())); i++) await run(page, 200);
  await run(page, 1500);
  for (const fitted of COMBINATIONS) {
    const name = ['player', ...fitted.map((b) => NAMES[b])].join('_');
    await page.evaluate((to) => (window as any).sideWalk.teleport(to), AT);
    await run(page, 500);
    await fit(page, fitted);
    await shot(page, `${name}-standing`);
    await page.keyboard.down('ArrowRight');
    await run(page, 430);
    await shot(page, `${name}-walking`);
    await page.keyboard.up('ArrowRight');
    await run(page, 400);
    await page.keyboard.press('Space');
    await run(page, 260);
    await shot(page, `${name}-jumping`);
    await run(page, 2000);
    await page.keyboard.down('ArrowLeft');
    await run(page, 600);
    await page.keyboard.up('ArrowLeft');
    await run(page, 600);
    await shot(page, `${name}-west`);
    console.log(`ok ${name}`);
  }
} finally {
  await browser.close();
  await server.close();
}
