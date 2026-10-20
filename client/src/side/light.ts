import type { LayerName, Rgb, SceneryManifest, TimeName } from './scenery';

/** When each time of day starts, in sim hours: `LIGHTING_SETS`' hours. */
export const TIME_STARTS: Record<TimeName, number> = { night: 21, morning: 5, afternoon: 11, evening: 17 };
const ORDER: TimeName[] = ['morning', 'afternoon', 'evening', 'night'];

/** How long one time of day takes to fade into the next, centred on its start. */
export const FADE_HOURS = 1;

/** Rooms are lamplit after dark. */
export const INSIDE: Record<TimeName, Rgb> = {
  morning: [1, 1, 1],
  afternoon: [1, 1, 1],
  evening: [0.97, 0.9, 0.82],
  night: [0.85, 0.76, 0.62],
};

/** How much of the sky's colour each distant layer takes, and how dark the foreground falls. */
export const SKY_SHARE: Partial<Record<LayerName, number>> = { far: 0.5, mid: 0.25 };
export const FOREGROUND_SHADE = 0.55;

export type Light = {
  tint: Rgb;
  sky: Rgb;
  haze: Rgb;
  hazeAmount: number;
  glow: number;
  inside: Rgb;
};

const modulo = (value: number, by: number) => ((value % by) + by) % by;
const smooth = (x: number) => x * x * (3 - 2 * x);

/** The two times of day an hour falls between, and how far it's gone into the second. */
export function timesAt(hour: number): { from: TimeName; to: TimeName; weight: number } {
  const half = FADE_HOURS / 2;
  for (const [i, to] of ORDER.entries()) {
    const since = modulo(hour - TIME_STARTS[to] + 12, 24) - 12;
    if (-half < since && since < half) {
      return { from: ORDER.at(i - 1)!, to, weight: smooth((since + half) / FADE_HOURS) };
    }
  }
  const since = (time: TimeName) => modulo(hour - TIME_STARTS[time], 24);
  const current = ORDER.reduce((latest, time) => (since(time) < since(latest) ? time : latest));
  return { from: current, to: current, weight: 0 };
}

const mix = (a: Rgb, b: Rgb, t: number, out: Rgb): Rgb => {
  for (let i = 0; i < 3; i++) out[i] = a[i] + (b[i] - a[i]) * t;
  return out;
};

export const emptyLight = (): Light => ({
  tint: [1, 1, 1],
  sky: [1, 1, 1],
  haze: [0, 0, 0],
  hazeAmount: 0,
  glow: 0,
  inside: [1, 1, 1],
});

/** The light at an hour of sim time, the manifest's times blended across each change. */
export function lightAt(hour: number, manifest: Pick<SceneryManifest, 'times'>, out = emptyLight()): Light {
  const { from, to, weight } = timesAt(hour);
  const [a, b] = [manifest.times[from], manifest.times[to]];
  mix(a.tint, b.tint, weight, out.tint);
  mix(a.sky, b.sky, weight, out.sky);
  for (let i = 0; i < 3; i++) out.haze[i] = (a.haze[i + 1] + (b.haze[i + 1] - a.haze[i + 1]) * weight) / 255;
  out.hazeAmount = a.haze[0] + (b.haze[0] - a.haze[0]) * weight;
  out.glow = a.glow + (b.glow - a.glow) * weight;
  mix(INSIDE[from], INSIDE[to], weight, out.inside);
  return out;
}

/** The tint for a street layer at its depth: distant ones take some of the sky's colour. */
export function layerTint(light: Light, layer: LayerName, out: Rgb): Rgb {
  if (layer === 'sky') return mix(light.sky, light.sky, 0, out);
  mix(light.tint, light.sky, SKY_SHARE[layer] ?? 0, out);
  if (layer === 'foreground') for (let i = 0; i < 3; i++) out[i] *= FOREGROUND_SHADE;
  return out;
}

/** How far a layer is hazed towards the haze colour: the far layer fully, the mid layer half. */
export function hazeOf(light: Light, layer: LayerName): number {
  if (layer === 'far') return light.hazeAmount;
  if (layer === 'mid') return light.hazeAmount / 2;
  return 0;
}

/** A colour as Phaser's 0xRRGGBB, each channel clamped to 0–1. */
export function colour([r, g, b]: Rgb): number {
  const byte = (c: number) => Math.round(Math.min(Math.max(c, 0), 1) * 255);
  return (byte(r) << 16) | (byte(g) << 8) | byte(b);
}

/** What a tint over 1 leaves to add: a second, additive copy brings the picture to the full tint. */
export function overflow([r, g, b]: Rgb): number {
  return colour([Math.max(r - 1, 0), Math.max(g - 1, 0), Math.max(b - 1, 0)]);
}
