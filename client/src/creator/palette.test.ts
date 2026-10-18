import { expect, it } from 'vitest';
import charactersPy from '../../../server/simile/art/characters.py?raw';
import palettePy from '../../../server/simile/art/palette.py?raw';
import schemaPy from '../../../server/simile/schema/npc.py?raw';
import {
  ACCESSORIES,
  BUILDS,
  DEFAULT_LOOK,
  HAIR_STYLES,
  PALETTE,
  SKIN_TONES,
  nearest,
} from './palette';

function members(enumName: string): string[] {
  const body = schemaPy.split(`class ${enumName}(StrEnum):`)[1].split('\n\n')[0];
  return [...body.matchAll(/= "(\w+)"/g)].map(([, value]) => value);
}

it('matches the sprite generator’s palette and options', () => {
  const block = palettePy.split('PALETTE: dict[str, str] = {')[1].split('}')[0];
  const palette = Object.fromEntries(
    [...block.matchAll(/"(\w+)": "(#[0-9a-f]{6})"/g)].map(([, name, hex]) => [name, hex]),
  );
  expect(PALETTE).toEqual(palette);
  expect(charactersPy).toContain(`SKIN_TONES = (${SKIN_TONES.map((s) => `"${s}"`).join(', ')})`);
  expect(HAIR_STYLES).toEqual(members('HairStyle'));
  expect(BUILDS).toEqual(members('Build'));
  expect(ACCESSORIES).toEqual(members('Accessory'));
  const player = Object.values(DEFAULT_LOOK)
    .flat()
    .map((part) => `"${part}"`)
    .join(', ');
  expect(charactersPy.replace(/\s+/g, ' ')).toContain(`PLAYER = _look( ${player} )`);
});

it('snaps a colour to the palette as the generator does', () => {
  expect(nearest('#e43b44')).toBe('red');
  expect(nearest('#e8b98f', SKIN_TONES)).toBe('peach');
  expect(nearest('#1c1b22')).toBe('espresso');
  expect(nearest('#d9645a')).toBe('pink');
});
