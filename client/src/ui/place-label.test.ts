// @vitest-environment jsdom
import { beforeEach, describe, expect, it } from 'vitest';
import type { TiledMap } from '../world/map';
import { NEW_PLACE_SECONDS, PlaceLabel } from './place-label';

const prop = (name: string, value: unknown) => ({ name, type: 'string', value });
const map = (properties: ReturnType<typeof prop>[], buildings: { name: string; label: string }[] = []): TiledMap => ({
  width: 1,
  height: 1,
  tilewidth: 1,
  tileheight: 1,
  properties,
  layers: [
    {
      name: 'buildings',
      type: 'objectgroup',
      objects: buildings.map(({ name, label }) => ({ name, type: 'building', properties: [prop('label', label)] })),
    },
  ],
});
const floor = (building: string, n: number) =>
  map([prop('kind', 'floor'), prop('building', building), prop('floor', n), prop('street', 'high_street')]);

/** content/street/'s, cut down: jsdom can't read the maps from disk. */
const MAPS = {
  high_street: map([prop('kind', 'street'), prop('label', 'High Street')], [{ name: 'noodle_bar', label: 'Golden Bowl Noodles' }]),
  noodle_bar_floor_0: floor('noodle_bar', 0),
  noodle_bar_floor_1: floor('noodle_bar', 1),
  metro: map([prop('kind', 'street'), prop('label', 'The Old Metro')]),
};

describe('PlaceLabel', () => {
  let root: HTMLElement;
  let label: PlaceLabel;
  const element = () => root.querySelector<HTMLElement>('.place-label')!;
  const shown = () => (element().hidden ? null : element().textContent);
  const standsOut = () => element().classList.contains('place-label-new');

  beforeEach(() => {
    root = document.createElement('div');
    label = new PlaceLabel(root, MAPS);
  });

  it('names the place, standing out for a moment, then settling', () => {
    label.update('high_street', 10);
    expect(shown()).toBe('High Street');
    expect(standsOut()).toBe(true);
    label.update('high_street', 10 + NEW_PLACE_SECONDS);
    expect(shown()).toBe('High Street');
    expect(standsOut()).toBe(false);
  });

  it('changes through a door and stands out again', () => {
    label.update('high_street', 0);
    label.update('high_street', 5);
    label.update('noodle_bar_floor_0', 6);
    expect(shown()).toBe('Golden Bowl Noodles');
    expect(standsOut()).toBe(true);
  });

  it('stays settled up the stairs, in the same building', () => {
    label.update('noodle_bar_floor_0', 0);
    label.update('noodle_bar_floor_1', NEW_PLACE_SECONDS);
    expect(shown()).toBe('Golden Bowl Noodles');
    expect(standsOut()).toBe(false);
  });

  it('changes between streets', () => {
    label.update('high_street', 0);
    label.update('metro', 1);
    expect(shown()).toBe('The Old Metro');
  });

  it('hides off the named maps', () => {
    label.update('high_street', 0);
    label.update('village', 1);
    expect(shown()).toBeNull();
    label.update(undefined, 2);
    expect(shown()).toBeNull();
    expect(standsOut()).toBe(false);
  });
});
