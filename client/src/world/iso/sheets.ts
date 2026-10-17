import type { Point } from '../view';
import type { SetLight } from './lighting';
import type { LightingSet } from './time-of-day';

export type SheetDirection = { name: string; row: number; vector: [x: number, y: number] };

/** `content/art/iso/characters/characters.json`: `server/simile/art/iso/README.md`. */
export type CharacterManifest = {
  format: number;
  frame: { width: number; height: number; anchor: [x: number, y: number] };
  columns: number;
  directions: SheetDirection[];
  animations: {
    walk: { fps: number; tiles_per_cycle: number; frames: Record<string, number[]> };
    idle: { fps: number; frames: Record<string, number[]> };
  };
  figure_m: number;
  sets: Record<LightingSet, SetLight>;
  characters: Record<string, { image: string; width: number; height: number }>;
};

const turn = (from: number, to: number) =>
  Math.abs(Math.atan2(Math.sin(to - from), Math.cos(to - from)));

export function directionFor(
  step: Point,
  directions: readonly SheetDirection[],
  previous: string,
): string {
  if (step.x === 0 && step.y === 0) return previous;
  const angle = Math.atan2(step.y, step.x);
  const off = ({ vector: [x, y] }: SheetDirection) => turn(angle, Math.atan2(y, x));
  return directions.reduce((best, each) => (off(each) < off(best) ? each : best)).name;
}

export function walkTimeScale(speed: number, walk: CharacterManifest['animations']['walk']): number {
  const frames = Object.values(walk.frames)[0].length;
  return (frames * speed) / walk.tiles_per_cycle / walk.fps;
}

const hash = (text: string) => [...text].reduce((sum, char) => (sum * 31 + char.charCodeAt(0)) >>> 0, 7);

export function sheetFor(id: string, sheets: readonly string[], player: string): string {
  if (sheets.includes(id)) return id;
  const residents = sheets.filter((sheet) => sheet !== player);
  return residents[hash(id) % residents.length] ?? player;
}
