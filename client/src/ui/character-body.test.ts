import { describe, expect, it } from 'vitest';
import type { Bionic, BodyPart } from '../net';
import { CHART, gradeOf, partDetails, PICTURES, pictureOf, PLACES } from './character-body';
import type { BodyRow } from './character-panel';
import { iconUrl } from './icons';

const PARTS = Object.keys(PLACES) as BodyPart[];
const BIONICS = Object.keys(PICTURES) as Bionic[];

const bionic = (part: BodyPart, fitted: Bionic, text: string = fitted): BodyRow => ({
  part,
  label: part,
  state: 'bionic',
  text,
  fitted,
});

describe('pictureOf', () => {
  it('shows their own organ, then its stitched socket once sold', () => {
    expect(pictureOf({ part: 'left_kidney', state: 'present' })).toBe('kidney');
    expect(pictureOf({ part: 'left_kidney', state: 'sold' })).toBe('kidney_sold');
    expect(pictureOf({ part: 'right_eye', state: 'sold' })).toBe('eye_sold');
  });

  it('shows every grade of a line alike, and stage 1’s legs as the hydraulic legs', () => {
    expect(['power_cell', 'power_cell_2', 'power_cell_3'].map((b) => pictureOf(bionic('stomach', b as Bionic)))).toEqual([
      'power_cell',
      'power_cell',
      'power_cell',
    ]);
    expect(pictureOf(bionic('legs', 'premium_legs'))).toBe('hydraulic_legs');
    expect(pictureOf(bionic('feet', 'spring_feet_2'))).toBe('spring_feet');
  });

  it('has a painted icon for every part, its socket, and every bionic', () => {
    const pictures = [
      ...PARTS.flatMap((part) => [pictureOf({ part, state: 'present' }), pictureOf({ part, state: 'sold' })]),
      ...BIONICS.map((b) => pictureOf(bionic('legs', b))),
    ];
    expect(pictures.filter((picture) => !iconUrl(picture))).toEqual([]);
  });
});

describe('partDetails', () => {
  it('says what a bionic is, its grade and what it does', () => {
    expect(partDetails(bionic('legs', 'bionic_legs_2', 'Bionic legs, grade 2'))).toEqual({
      title: 'legs',
      state: 'bionic',
      status: 'Bionic legs, grade 2',
      lines: ['A bionic in place of your legs, grade 2 of 3.', 'Run faster, jump further and kick harder than the first grade.'],
    });
    expect(gradeOf('datajack')).toBeUndefined();
  });

  it('says whether a part is theirs or sold', () => {
    const kidney: BodyRow = { part: 'left_kidney', label: 'Left kidney', state: 'present', text: 'Your own' };
    expect(partDetails(kidney).lines).toEqual(['One of your own kidneys. You can live on one.']);
    expect(partDetails({ ...kidney, state: 'sold', text: 'Sold' })).toMatchObject({ status: 'Sold' });
  });
});

describe('PLACES', () => {
  it('keeps every part on the chart, none overlapping another', () => {
    const boxes = PARTS.map((part) => {
      const { x, y, w, h } = PLACES[part];
      return [x - w / 2, y - h / 2, x + w / 2, y + h / 2];
    });
    for (const [left, top, right, bottom] of boxes) {
      expect(left >= 0 && top >= 0 && right <= CHART.width && bottom <= CHART.height).toBe(true);
    }
    const overlapping = boxes.flatMap((a, i) =>
      boxes.slice(i + 1).flatMap((b, j) =>
        a[0] < b[2] && b[0] < a[2] && a[1] < b[3] && b[1] < a[3] ? [[PARTS[i], PARTS[i + 1 + j]]] : [],
      ),
    );
    expect(overlapping).toEqual([]);
  });
});
