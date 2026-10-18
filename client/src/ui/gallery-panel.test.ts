// @vitest-environment jsdom
import { afterEach, beforeEach, expect, it } from 'vitest';
import { server, type Frame, type Position } from '../net';
import type { Interactable } from '../world/interactables';
import { GalleryFrames } from '../world/iso/paintings';
import { mapOf, tileOf } from '../world/map';
import { GalleryPanel } from './gallery-panel';

/** Two of the gallery map's frames: tests under jsdom can't read the maps from disk. */
const frameAt = (id: string, x: number): Interactable => ({
  id,
  kind: 'painting',
  label: 'Painting',
  map: 'gallery',
  stand: [
    { x, y: 11 },
    { x: x + 1, y: 11 },
  ],
  prompt: 'Look at the painting',
});
const ON_THE_MAP = [frameAt('painting_11', 19), frameAt('painting_10', 11)];

function find(map: string, position: Position | undefined): Interactable | undefined {
  if (!position || mapOf(position) !== map) return undefined;
  const { x, y } = tileOf(position);
  return ON_THE_MAP.find((item) => item.map === map && item.stand.some((tile) => tile.x === x && tile.y === y));
}

const HARBOUR: Frame = {
  id: 'painting_11',
  map: 'gallery',
  painting: {
    work_id: 'kofi-1',
    title: 'Harbour at Dusk',
    artist: { id: 'kofi', name: 'Kofi Mensah' },
    statement: 'Every boat comes home eventually.',
    image: '/api/gallery/kofi-1.png',
  },
};
const EMPTY: Frame = { id: 'painting_10', map: 'gallery', painting: null };

const AT_HARBOUR = { x: 19, y: 11, map: 'gallery' };
const BESIDE_IT = { x: 20, y: 11, map: 'gallery' };
const AT_EMPTY = { x: 12, y: 11, map: 'gallery' };
const MID_ROOM = { x: 16, y: 15, map: 'gallery' };

let frames: GalleryFrames;
let panel: GalleryPanel;

const section = () => document.querySelector<HTMLElement>('.gallery')!;
const text = (selector: string) => document.querySelector(`.gallery ${selector}`)!.textContent;

function paintings(list: Frame[]): void {
  server.dispatch(JSON.stringify({ type: 'paintings', frames: list }));
}

function press(key: string): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  (document.activeElement ?? section()).dispatchEvent(event);
  return event;
}

beforeEach(() => {
  frames = new GalleryFrames(server);
  panel = new GalleryPanel(document.body, frames, find);
  paintings([HARBOUR, EMPTY]);
});

afterEach(() => {
  panel.stop();
  document.body.replaceChildren();
});

it('hints at the painting the player stands at, and at an empty frame', () => {
  panel.update(AT_HARBOUR);
  expect(panel.hint.hidden).toBe(false);
  expect(panel.hint.textContent).toBe('Press E to look at “Harbour at Dusk” by Kofi Mensah.');

  panel.update(AT_EMPTY);
  expect(panel.hint.textContent).toBe('This frame is empty.');

  panel.update(MID_ROOM);
  expect(panel.hint.hidden).toBe(true);
});

it('opens at a painting with it large, its title, artist and statement', () => {
  expect(panel.look(BESIDE_IT)).toBe(true);

  expect(section().hidden).toBe(false);
  expect(document.activeElement).toBe(section());
  expect(text('header b')).toBe('Harbour at Dusk');
  expect(text('small')).toBe('by Kofi Mensah');
  expect(text('p')).toBe('Every boat comes home eventually.');
  const image = document.querySelector<HTMLImageElement>('.gallery img')!;
  expect(image.getAttribute('src')).toBe('/api/gallery/kofi-1.png');
  expect(image.alt).toBe('Harbour at Dusk');

  panel.update(BESIDE_IT);
  expect(panel.hint.hidden).toBe(true);
});

it('opens nothing at an empty frame, away from the frames or on another map', () => {
  expect(panel.look(AT_EMPTY)).toBe(false);
  expect(panel.look(MID_ROOM)).toBe(false);
  expect(panel.look({ x: 19, y: 11 })).toBe(false);
  expect(panel.look(undefined)).toBe(false);
  expect(section().hidden).toBe(true);
});

it('closes on Esc or E, without the keys reaching the game', () => {
  let reached = 0;
  const count = () => reached++;
  window.addEventListener('keydown', count);

  panel.look(AT_HARBOUR);
  press('Escape');
  expect(section().hidden).toBe(true);

  panel.look(AT_HARBOUR);
  press('ArrowLeft');
  expect(section().hidden).toBe(false);
  press('e');
  expect(section().hidden).toBe(true);

  window.removeEventListener('keydown', count);
  expect(reached).toBe(0);
});

it('closes when the player steps away from the frame', () => {
  panel.look(AT_HARBOUR);
  panel.update(BESIDE_IT);
  expect(panel.isOpen).toBe(true);

  panel.update({ x: 19, y: 12, map: 'gallery' });
  expect(panel.isOpen).toBe(false);
});

it('shows the new painting when one replaces it, and closes if the frame empties', () => {
  panel.look(AT_HARBOUR);
  const next = {
    ...HARBOUR.painting!,
    work_id: 'odalys-1',
    title: 'Shared Table',
    image: '/api/gallery/odalys-1.png',
  };
  paintings([{ ...HARBOUR, painting: next }, EMPTY]);

  expect(text('header b')).toBe('Shared Table');
  expect(document.querySelector('.gallery img')!.getAttribute('src')).toBe('/api/gallery/odalys-1.png');

  paintings([{ ...HARBOUR, painting: null }, EMPTY]);
  expect(panel.isOpen).toBe(false);
});
