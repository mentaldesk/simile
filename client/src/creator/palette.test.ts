import { expect, it } from 'vitest';
import palettePy from '../../../server/simile/characters/palette.py?raw';
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

it('matches the server’s palette, options and player', () => {
  const block = palettePy.split('PALETTE: dict[str, str] = {')[1].split('}')[0];
  const palette = Object.fromEntries(
    [...block.matchAll(/"(\w+)": "(#[0-9a-f]{6})"/g)].map(([, name, hex]) => [name, hex]),
  );
  expect(PALETTE).toEqual(palette);
  expect(palettePy).toContain(`SKIN_TONES = (${SKIN_TONES.map((s) => `"${s}"`).join(', ')})`);
  expect(HAIR_STYLES).toEqual(members('HairStyle'));
  expect(BUILDS).toEqual(members('Build'));
  expect(ACCESSORIES).toEqual(members('Accessory'));
  const player = palettePy.split('PLAYER = Appearance.model_validate(')[1].split('\n)')[0];
  expect(JSON.parse(player.replace(/,(\s*[}\]])/g, '$1'))).toEqual(DEFAULT_LOOK);
});

it('snaps a colour to the palette as the server does', () => {
  expect(nearest('#e43b44')).toBe('red');
  expect(nearest('#e8b98f', SKIN_TONES)).toBe('peach');
  expect(nearest('#1c1b22')).toBe('espresso');
  expect(nearest('#d9645a')).toBe('pink');
});
