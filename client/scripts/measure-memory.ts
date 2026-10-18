// Renderer and GPU process memory over lighting changes and gallery visits at a fast clock: macOS only.
// Start the sim server and `npm run dev` first, then:
//   node scripts/measure-memory.ts [--url http://localhost:5173/?play] [--width 2560 --height 1440 --dpr 2] [--samples out.jsonl]
import { execFileSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';
import { parseArgs } from 'node:util';
import { chromium, type Page } from 'playwright';

const { values: options } = parseArgs({
  options: {
    url: { type: 'string', default: 'http://localhost:5173/?play' },
    width: { type: 'string', default: '2560' },
    height: { type: 'string', default: '1440' },
    dpr: { type: 'string', default: '2' },
    samples: { type: 'string' },
  },
});
const viewport = { width: Number(options.width), height: Number(options.height) };
const deviceScaleFactor = Number(options.dpr);
const SPEED = 300;
const START = Date.parse('2026-06-01T15:45:00Z');
const VISITS = 5;
const STEADY_SECONDS = 30;
const BELOW_GALLERY = { x: 40, y: 34, map: 'village' };
const MB = 1024 * 1024;

const FOOTPRINT = `
import ctypes, json, sys
libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
class Info(ctypes.Structure):
    _fields_ = [("uuid", ctypes.c_uint8 * 16)] + [(f"f{i}", ctypes.c_uint64) for i in range(35)]
out = {}
for pid in sys.argv[1:]:
    info = Info()
    if libc.proc_pid_rusage(int(pid), 4, ctypes.byref(info)) == 0:
        out[pid] = [info.f7, info.f28]
print(json.dumps(out))
`;

type Sample = { t: number; phase: string; renderer: number; gpu: number; rendererPeak: number; gpuPeak: number };

const browser = await chromium.launch({ channel: 'chromium', args: ['--enable-precise-memory-info'] });
const context = await browser.newContext({ viewport, deviceScaleFactor });
const page = await context.newPage();
const cdp = await browser.newBrowserCDPSession();
const errors: string[] = [];
page.on('console', (message) => {
  if (message.type() === 'error' || message.type() === 'warning') errors.push(message.text());
});

let clockStart: number | undefined;
const simTime = () => new Date(START + SPEED * (Date.now() - (clockStart ??= Date.now()))).toISOString();
await page.routeWebSocket(/\/ws/, (ws) => {
  const server = ws.connectToServer();
  server.onMessage((message) => {
    const parsed = JSON.parse(String(message));
    if (parsed.type === 'snapshot') parsed.time = simTime();
    if (parsed.type === 'clock') Object.assign(parsed, { time: simTime(), speed: SPEED });
    ws.send(JSON.stringify(parsed));
  });
});

const samples: Sample[] = [];
let phase = 'loading';
const begun = Date.now();
async function sample(): Promise<void> {
  const { processInfo } = (await cdp.send('SystemInfo.getProcessInfo')) as {
    processInfo: { type: string; id: number }[];
  };
  const pids = processInfo.filter(({ type }) => type === 'renderer' || type === 'GPU');
  const sizes = JSON.parse(
    execFileSync('python3', ['-I', '-c', FOOTPRINT, ...pids.map(({ id }) => String(id))], { encoding: 'utf8' }),
  ) as Record<string, [number, number]>;
  const of = (type: string) =>
    pids
      .filter((process) => process.type === type)
      .map(({ id }) => sizes[id] ?? [0, 0])
      .reduce((largest, size) => (size[0] > largest[0] ? size : largest), [0, 0]);
  const [renderer, rendererPeak] = of('renderer');
  const [gpu, gpuPeak] = of('GPU');
  samples.push({ t: (Date.now() - begun) / 1000, phase, renderer, gpu, rendererPeak, gpuPeak });
}
const sampling = setInterval(() => void sample(), 500);

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));
const mapOf = (page: Page) =>
  page.evaluate(async () => (await import('/src/world/index.ts')).world.player?.map) as Promise<string | undefined>;

async function hold(keys: string[], until: () => Promise<boolean>, timeoutMs: number): Promise<void> {
  for (const key of keys) await page.keyboard.down(key);
  const deadline = Date.now() + timeoutMs;
  while (!(await until()) && Date.now() < deadline) await sleep(50);
  for (const key of keys) await page.keyboard.up(key);
}

await page.goto(options.url);
await page.waitForFunction(async () => (await import('/src/world/index.ts')).world.player !== undefined);
const gl = await page.evaluate(() => {
  const context = document.querySelector('canvas')?.getContext('webgl');
  const info = context?.getExtension('WEBGL_debug_renderer_info');
  return info ? String(context!.getParameter(info.UNMASKED_RENDERER_WEBGL)) : 'unknown';
});
await sleep(10_000);

for (let visit = 1; visit <= VISITS; visit++) {
  phase = `visit ${visit}: outside`;
  await page.evaluate(
    async (position) => (await import('/src/world/index.ts')).world.player?.place(position),
    BELOW_GALLERY,
  );
  await sleep(2000);
  await hold(['ArrowUp', 'ArrowRight'], async () => (await mapOf(page)) === 'gallery', 10_000);
  phase = `visit ${visit}: inside`;
  await sleep(8000);
  await hold(['ArrowUp', 'ArrowRight'], async () => false, 400);
  await hold(['ArrowDown', 'ArrowLeft'], async () => (await mapOf(page)) === 'village', 10_000);
  phase = `visit ${visit}: left`;
  await sleep(8000);
}
phase = 'steady';
await sleep(STEADY_SECONDS * 1000);
clearInterval(sampling);
await sample();
await browser.close();

const median = (values: number[]) => values.sort((a, b) => a - b)[Math.floor(values.length / 2)] ?? 0;
const steady = samples.filter(({ phase }) => phase === 'steady');
const last = samples.at(-1)!;
const summary = {
  gl,
  canvas: `${viewport.width * deviceScaleFactor}x${viewport.height * deviceScaleFactor}`,
  speed: SPEED,
  seconds: last.t,
  rendererMB: {
    peak: Math.round(last.rendererPeak / MB),
    steady: Math.round(median(steady.map(({ renderer }) => renderer)) / MB),
  },
  gpuMB: {
    peak: Math.round(last.gpuPeak / MB),
    steady: Math.round(median(steady.map(({ gpu }) => gpu)) / MB),
  },
  errors: [...new Set(errors)],
};
if (options.samples) writeFileSync(options.samples, samples.map((each) => JSON.stringify(each)).join('\n') + '\n');
console.log(JSON.stringify(summary, null, 2));
