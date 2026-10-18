import { describe, expect, it } from 'vitest';
import { Draft } from './draft';
import { character } from './character.fixture';
import { CORE_VALUES } from './values';

const written = (overrides = {}) => ({
  character: character(overrides),
  suggestions: [],
  notes: [],
  warnings: [],
});

describe('a new draft', () => {
  it('starts with nothing locked and nothing to save', () => {
    const draft = Draft.blank();
    expect(draft.locks.size).toBe(0);
    expect(draft.written).toBe(false);
    expect(draft.dirty).toBe(false);
    expect(draft.problems()).toEqual(['Write the character first.']);
  });

  it('asks for a whole character when nothing is set', () => {
    expect(Draft.blank().brief()).toEqual({ source: 'player' });
  });

  it('locks what the player sets and puts it in the brief', () => {
    const draft = Draft.blank();
    draft.edit('background', { name: 'Wren Abernethy', gender: 'woman', origin: '' });
    draft.edit('look', { appearance: character().appearance });
    expect(draft.locked('background')).toBe(true);
    expect(draft.brief()).toEqual({
      source: 'player',
      name: 'Wren Abernethy',
      gender: 'woman',
      appearance: character().appearance,
    });
  });

  it('keeps born-here as a locked arrival of null', () => {
    const draft = Draft.blank();
    draft.edit('background', { arrival: null });
    expect(draft.brief()).toEqual({ source: 'player', arrival: null });
  });

  it('locks all 24 values once the player moves them', () => {
    const draft = Draft.blank();
    draft.values.setTrait('openness', 2);
    draft.edit('values', { values: draft.values.values() });
    expect(Object.keys(draft.brief().values ?? {})).toEqual(CORE_VALUES);
  });

  it('leaves an unfinished voice out of the brief', () => {
    const draft = Draft.blank();
    const voice = { ...character().voice, reference_line: ' ' };
    draft.edit('voice', { voice });
    expect(draft.brief().voice).toBeUndefined();
  });

  it('can be saved once it’s written', () => {
    const draft = Draft.blank();
    draft.apply(written());
    expect(draft.written).toBe(true);
    expect(draft.dirty).toBe(true);
    expect(draft.problems()).toEqual([]);
  });
});

describe('rerolling', () => {
  it('asks for every unlocked section', () => {
    const draft = Draft.of(character());
    expect(draft.rerolls(draft.unlocked())).toEqual([
      'name',
      'identity',
      'values',
      'past',
      'biography',
      'hooks',
      'voice',
      'appearance',
    ]);
  });

  it('never asks for a locked section', () => {
    const draft = Draft.of(character());
    draft.setLocked('look', true);
    draft.setLocked('voice', true);
    expect(draft.rerolls(['look', 'voice'])).toEqual([]);
    expect(draft.rerolls(draft.unlocked())).not.toContain('appearance');
  });

  it('rerolls life events and ties with the biography', () => {
    expect(Draft.of(character()).rerolls(['biography'])).toEqual(['past', 'biography', 'hooks']);
  });

  it('brings a new biography with a new background unless the biography is locked', () => {
    const draft = Draft.of(character());
    expect(draft.rerolls(['background'])).toEqual([
      'name',
      'identity',
      'past',
      'biography',
      'hooks',
    ]);
    draft.setLocked('biography', true);
    expect(draft.rerolls(['background'])).toEqual(['name', 'identity']);
  });

  it('locks a section the player edits, so a reroll keeps the edit', () => {
    const draft = Draft.of(character());
    draft.edit('biography', { persona: 'Changed by hand.' });
    expect(draft.rerolls(draft.unlocked())).not.toContain('biography');
  });

  it('keeps the critic’s suggestions through a reroll it didn’t read', () => {
    const draft = Draft.of(character());
    const suggestion = { field: 'persona', current: 'a', suggested: 'b' };
    draft.apply({ ...written(), suggestions: [suggestion], notes: ['note'] });
    draft.apply(written({ voice: { ...character().voice, reference_line: 'New line.' } }), [
      'voice',
    ]);
    expect(draft.suggestions).toEqual([suggestion]);
    draft.apply(written(), ['past', 'biography', 'hooks']);
    expect(draft.suggestions).toEqual([]);
    expect(draft.notes).toEqual([]);
  });

  it('fits the value sliders again when a reroll draws new values', () => {
    const draft = Draft.of(character());
    const values = Object.fromEntries(CORE_VALUES.map((v) => [v, 0.8]));
    draft.apply(written({ values }), ['values']);
    expect(draft.values.values()).toEqual(values);
  });
});

describe('the critic’s suggestions', () => {
  it('applies one to the field it names, and locks the biography', () => {
    const draft = Draft.of(character({ past: [character().past[0], character().past[0]] }));
    const suggestions = [
      { field: 'past[1]', current: 'I took the mower apart.', suggested: 'I sold the mower.' },
      { field: 'hooks[0]', current: '', suggested: 'We both wanted the yard.' },
      { field: 'interests', current: '', suggested: 'diesel engines; knots' },
      { field: 'persona', current: '', suggested: 'Blunt.' },
    ];
    draft.apply({ ...written(draft.work), suggestions });
    suggestions.forEach((s) => draft.accept(s));
    expect(draft.work.past?.map((m) => m.content)).toEqual([
      'I took the mower apart.',
      'I sold the mower.',
    ]);
    expect(draft.work.hooks?.[0].description).toBe('We both wanted the yard.');
    expect(draft.work.interests).toEqual(['diesel engines', 'knots']);
    expect(draft.work.persona).toBe('Blunt.');
    expect(draft.suggestions).toEqual([]);
    expect(draft.locked('biography')).toBe(true);
  });

  it('drops one that’s ignored and changes nothing', () => {
    const draft = Draft.of(character());
    const suggestion = { field: 'persona', current: '', suggested: 'Blunt.' };
    draft.apply({ ...written(), suggestions: [suggestion] });
    draft.ignore(suggestion);
    expect(draft.suggestions).toEqual([]);
    expect(draft.work.persona).toBe(character().persona);
  });
});

describe('validation before saving', () => {
  it('lists what the server would refuse', () => {
    const draft = Draft.of(character());
    draft.edit('background', { name: ' ', birth_year: 2000, arrival: { age: 30, reason: '' } });
    draft.edit('biography', {
      persona: '',
      past: [{ age: 40, content: '', salience: 0.5, valence: 0 }],
      hooks: [{ kind: 'rival', side: 'mutual', description: '' }],
      craft: { medium: 'mural', form: '' },
    });
    expect(draft.problems(2026)).toEqual([
      'Give them a name.',
      'Say why they came.',
      'They arrived at 30, but they’re 26.',
      'The persona is empty.',
      'Life event 1 is empty.',
      'Life event 1 happened at 40, but they’re 26.',
      'Tie 1 is empty.',
      'Say what they make, or choose nothing.',
    ]);
  });

  it('refuses an age over 120', () => {
    const draft = Draft.of(character());
    draft.edit('background', { birth_year: 1900 });
    expect(draft.problems(2026)).toEqual(['Their birth year has to make them 0 to 120.']);
  });
});

describe('saving', () => {
  it('is clean once saved, and dirty after an edit', () => {
    const draft = Draft.of(character());
    expect(draft.dirty).toBe(false);
    draft.edit('look', { appearance: { ...character().appearance, build: 'broad' } });
    expect(draft.dirty).toBe(true);
    draft.markSaved(character({ appearance: draft.work.appearance!, version: 2 }));
    expect(draft.dirty).toBe(false);
  });

  it('isn’t dirty over the fields the server sets', () => {
    const draft = Draft.of(character());
    draft.work.version = 7;
    draft.work.updated = '2026-10-19T00:00:00Z';
    expect(draft.dirty).toBe(false);
  });

  it('keeps a designed voice’s description, which a pick leaves alone', () => {
    const draft = Draft.of(character());
    const picked = character({
      version: 2,
      voice: { ...character().voice, reference_clip: 'clips/wren_abernethy.wav' },
    });
    draft.markVoice(picked, 'A new description.');
    expect(draft.work.voice).toEqual({ ...picked.voice, description: 'A new description.' });
    expect(draft.work.version).toBe(2);
    expect(draft.dirty).toBe(true);
  });

  it('isn’t dirty after a library pick', () => {
    const draft = Draft.of(character());
    const picked = character({
      version: 2,
      voice: {
        ...character().voice,
        reference_line: 'A library line.',
        reference_clip: 'clips/w.wav',
      },
    });
    draft.markVoice(picked);
    expect(draft.dirty).toBe(false);
    expect(draft.work.voice?.reference_line).toBe('A library line.');
  });
});
