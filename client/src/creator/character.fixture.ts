import type { Character } from './character';
import { CORE_VALUES } from './values';

export function character(overrides: Partial<Character> = {}): Character {
  return {
    id: 'wren_abernethy',
    name: 'Wren Abernethy',
    birth_year: 1980,
    gender: 'woman',
    origin: 'Scotland',
    arrival: { age: 30, reason: 'for a job' },
    occupation: 'Ferry mechanic',
    values: Object.fromEntries(CORE_VALUES.map((v, i) => [v, (i % 10) / 10])),
    backstory: 'She fixes engines nobody else will touch.',
    persona: 'Blunt, quick and kind when it costs her nothing.',
    speaking_style: 'Short sentences, trade words.',
    interests: ['diesel engines', 'tide tables'],
    past: [{ age: 12, content: 'I took the mower apart.', salience: 0.5, valence: 0.4 }],
    hooks: [{ kind: 'rival', side: 'mutual', description: 'We bid for the same contract.' }],
    traits: { sociability: 0.4, negativity_bias: 0.5, forgiveness: 0.6, first_impressions: 0.5 },
    appearance: {
      skin: '#c28569',
      hair_style: 'bun',
      hair_colour: '#181425',
      top_colour: '#265c42',
      bottom_colour: '#3a4466',
      shoe_colour: '#181425',
      build: 'average',
      accessories: [],
    },
    voice: {
      description: 'A Fife accent. A woman in her forties, low and even.',
      reference_line:
        'The ferry engine runs rough in the cold, so I strip the injectors every winter.',
      reference_clip: null,
      needs_recording: false,
    },
    craft: null,
    source: 'player',
    created: '2026-10-18T09:00:00Z',
    updated: '2026-10-18T09:00:00Z',
    version: 1,
    ...overrides,
  };
}
