// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { server, type Position, type Wall } from '../net';
import { MuralWalls, type MuralView } from '../world/iso/murals';
import { MuralPanel } from './mural-panel';
import { setMaps } from './side-view';

const GRIND: Wall = {
  id: 'daily_grind',
  x: 28,
  y: 10,
  width: 3,
  face: 'south',
  bottom: 1.05,
  top: 1.9,
  mural: {
    work_id: 'mars',
    title: 'Red Horizon',
    artist: { id: 'kofi', name: 'Kofi Mensah' },
    statement: 'Mars is a billionaire’s lifeboat.',
    image: '/api/works/mars.png',
  },
};
const BLANK: Wall = { ...GRIND, id: 'corner_shop', x: 21, y: 6, face: 'east', mural: null };

const IN_FRONT = { x: 29, y: 12 };
const ACROSS_THE_SQUARE = { x: 29, y: 20 };

let walls: MuralWalls;
let view: MuralView | undefined;
let panel: MuralPanel;

const section = () => document.querySelector<HTMLElement>('.mural')!;
const hint = () => panel.hint;
const text = (selector: string) => document.querySelector(`.mural ${selector}`)!.textContent;

function murals(list: Wall[]): void {
  server.dispatch(JSON.stringify({ type: 'murals', walls: list }));
}

function press(key: string): KeyboardEvent {
  const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
  (document.activeElement ?? section()).dispatchEvent(event);
  return event;
}

beforeEach(() => {
  walls = new MuralWalls(server);
  view = { wallAt: (point) => (point.x === 1 && point.y === 1 ? 'daily_grind' : undefined) };
  panel = new MuralPanel(document.body, walls, () => view);
  murals([GRIND, BLANK]);
});

afterEach(() => {
  panel.stop();
  document.body.replaceChildren();
});

it('hints at a painted wall the player stands in front of', () => {
  panel.update(IN_FRONT);
  expect(hint().hidden).toBe(false);
  expect(hint().textContent).toBe('Press E to look at “Red Horizon”.');

  panel.update(ACROSS_THE_SQUARE);
  expect(hint().hidden).toBe(true);

  panel.update(IN_FRONT, false);
  expect(hint().hidden).toBe(true);
});

it('changes the hint when the wall is painted over', () => {
  panel.update(IN_FRONT);
  murals([{ ...GRIND, mural: { ...GRIND.mural!, work_id: 'river', title: 'Slow River' } }, BLANK]);
  panel.update(IN_FRONT);

  expect(hint().textContent).toBe('Press E to look at “Slow River”.');
});

it('opens near a wall with its picture, title, artist and statement', () => {
  expect(panel.look(IN_FRONT)).toBe(true);

  expect(section().hidden).toBe(false);
  expect(document.activeElement).toBe(section());
  expect(text('header b')).toBe('Red Horizon');
  expect(text('small')).toBe('by Kofi Mensah');
  expect(text('p')).toBe('Mars is a billionaire’s lifeboat.');
  const image = document.querySelector<HTMLImageElement>('.mural img')!;
  expect(image.getAttribute('src')).toBe('/api/works/mars.png');
  expect(image.alt).toBe('Red Horizon');

  panel.update(IN_FRONT);
  expect(hint().hidden).toBe(true);
});

it('opens nothing away from a painted wall', () => {
  expect(panel.look(ACROSS_THE_SQUARE)).toBe(false);
  expect(panel.look({ x: 22, y: 8 })).toBe(false);
  expect(section().hidden).toBe(true);
});

it('opens nothing while no scene draws murals', () => {
  view = undefined;
  panel.update(IN_FRONT);

  expect(hint().hidden).toBe(true);
  expect(panel.look(IN_FRONT)).toBe(false);
  expect(panel.click({ x: 1, y: 1 }, IN_FRONT)).toBe(false);
});

it('closes on Esc or E, without the keys reaching the game', () => {
  let reached = 0;
  const count = () => reached++;
  window.addEventListener('keydown', count);

  panel.look(IN_FRONT);
  press('Escape');
  expect(section().hidden).toBe(true);

  panel.look(IN_FRONT);
  press('ArrowLeft');
  expect(section().hidden).toBe(false);
  press('e');
  expect(section().hidden).toBe(true);

  window.removeEventListener('keydown', count);
  expect(reached).toBe(0);
});

it('closes when the player walks away from the wall', () => {
  panel.look(IN_FRONT);
  panel.update({ x: 29, y: 13 });
  expect(panel.isOpen).toBe(true);

  panel.update(ACROSS_THE_SQUARE);
  expect(panel.isOpen).toBe(false);
});

it('closes when the player goes inside, and hints at nothing there', () => {
  panel.click({ x: 1, y: 1 }, ACROSS_THE_SQUARE);
  panel.update({ ...ACROSS_THE_SQUARE, map: 'coffee_shop' });
  expect(panel.isOpen).toBe(false);
  panel.update({ ...IN_FRONT, map: 'coffee_shop' });
  expect(hint().hidden).toBe(true);
});

it('opens a mural clicked from across the square, until the player walks off', () => {
  expect(panel.click({ x: 2, y: 2 }, ACROSS_THE_SQUARE)).toBe(false);
  expect(panel.click({ x: 1, y: 1 }, ACROSS_THE_SQUARE)).toBe(true);
  expect(text('header b')).toBe('Red Horizon');

  panel.update({ x: 29, y: 19.5 });
  expect(panel.isOpen).toBe(true);

  panel.update({ x: 29, y: 18 });
  expect(panel.isOpen).toBe(false);
});

it('shows the new mural when the wall is painted over, and closes when it goes blank', () => {
  panel.look(IN_FRONT);
  const over = {
    ...GRIND.mural!,
    work_id: 'river',
    title: 'Slow River',
    image: '/api/works/river.png',
  };
  murals([{ ...GRIND, mural: over }, BLANK]);

  expect(text('header b')).toBe('Slow River');
  expect(document.querySelector('.mural img')!.getAttribute('src')).toBe('/api/works/river.png');

  murals([{ ...GRIND, mural: null }, BLANK]);
  expect(panel.isOpen).toBe(false);
});

describe('on a side-view map', () => {
  const HIGH_STREET = 'high_street';
  /** content/street/high_street.tmj's wall, along cells 27 to 29. */
  const ALONG: Wall = { ...GRIND, map: HIGH_STREET, x: 27, y: 15 };
  const street = (x: number, y = 15): Position => ({ x, y, map: HIGH_STREET });
  let unset: () => void;

  beforeEach(() => {
    const view = [{ name: 'view', type: 'string', value: 'side' }];
    const map = { width: 84, height: 20, tilewidth: 16, tileheight: 16, layers: [] };
    unset = setMaps({ [HIGH_STREET]: { ...map, properties: view } });
    murals([ALONG]);
  });

  afterEach(() => unset());

  it('hints within reach along the street of either end of the wall', () => {
    const hinted = [23, 24, 28, 32, 33].map((x) => {
      panel.update(street(x));
      return !hint().hidden;
    });

    expect(hinted).toEqual([false, true, true, true, false]);
  });

  it('reaches nothing from inside the building behind the wall', () => {
    panel.update({ x: 3, y: 2, map: 'coffee_shop_floor_0' });

    expect(hint().hidden).toBe(true);
    expect(panel.look({ x: 3, y: 2, map: 'coffee_shop_floor_0' })).toBe(false);
  });

  it('closes once the player walks a tile along from where it opened, out of reach', () => {
    expect(panel.look(street(32))).toBe(true);
    panel.update(street(33, 12));
    expect(panel.isOpen).toBe(true);

    panel.update(street(34));
    expect(panel.isOpen).toBe(false);
  });
});
