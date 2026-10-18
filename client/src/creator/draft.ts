import type { Brief, Suggestion, Written } from './api';
import type { Character } from './character';
import { DEFAULT_LOOK } from './palette';
import { CORE_VALUES, ValueModel } from './values';

export const SECTIONS = ['look', 'values', 'background', 'biography', 'voice'] as const;
export type Section = (typeof SECTIONS)[number];

export const TITLES: Record<Section, string> = {
  look: 'Look',
  values: 'Values',
  background: 'Background',
  biography: 'Biography',
  voice: 'Voice',
};

type Field = keyof Character;

export const FIELDS: Record<Section, readonly Field[]> = {
  look: ['appearance'],
  values: ['values', 'traits'],
  background: ['name', 'birth_year', 'gender', 'origin', 'arrival', 'occupation'],
  biography: [
    'past',
    'backstory',
    'persona',
    'speaking_style',
    'mannerisms',
    'interests',
    'craft',
    'hooks',
  ],
  voice: ['voice'],
};

/** A reroll draws the facts behind the biography again, so life events and ties go with it. */
const REROLLS: Record<Section, readonly string[]> = {
  look: ['appearance'],
  values: ['values'],
  background: ['name', 'identity'],
  biography: ['past', 'biography', 'hooks'],
  voice: ['voice'],
};
const ORDER = ['name', 'identity', 'values', 'past', 'biography', 'hooks', 'voice', 'appearance'];
const CRITIQUED = new Set(['past', 'biography', 'hooks']);
const SERVER_SET: readonly Field[] = ['source', 'created', 'updated', 'version'];
export const MAX_MANNERISMS = 3;
const MANNERISM_LENGTH = 120;

export type Work = Partial<Character>;

export class Draft {
  work: Work;
  saved: Character | null;
  readonly locks = new Set<Section>();
  values: ValueModel;
  suggestions: Suggestion[] = [];
  notes: string[] = [];
  warnings: string[] = [];

  private constructor(work: Work, saved: Character | null, values: ValueModel) {
    this.work = work;
    this.saved = saved;
    this.values = values;
  }

  static blank(random: () => number = Math.random): Draft {
    const values = ValueModel.random(random);
    return new Draft({ appearance: clone(DEFAULT_LOOK), values: values.values() }, null, values);
  }

  static of(character: Character): Draft {
    return new Draft(clone(character), clone(character), ValueModel.fit(character.values));
  }

  get written(): boolean {
    return this.work.id !== undefined && this.work.backstory !== undefined;
  }

  get dirty(): boolean {
    if (!this.saved) return this.written;
    return canonical(editable(this.work)) !== canonical(editable(this.saved));
  }

  locked(section: Section): boolean {
    return this.locks.has(section);
  }

  setLocked(section: Section, locked: boolean): void {
    if (locked) this.locks.add(section);
    else this.locks.delete(section);
  }

  edit(section: Section, patch: Work): void {
    Object.assign(this.work, patch);
    this.locks.add(section);
  }

  brief(): Brief {
    const brief: Brief = { source: 'player' };
    const set = (field: Field) => {
      const value = this.work[field];
      if (value === undefined || value === '' || (Array.isArray(value) && !value.length)) return;
      Object.assign(brief, { [field]: clone(value) });
    };
    for (const section of this.locks) {
      if (section === 'values') {
        brief.values = { ...this.work.values };
      } else if (section === 'voice') {
        const voice = this.work.voice;
        if (voice?.description.trim() && voice.reference_line.trim()) brief.voice = clone(voice);
      } else {
        FIELDS[section].filter((field) => field !== 'traits').forEach(set);
      }
    }
    return brief;
  }

  /** A new background brings a new biography, unless the biography is locked. */
  rerolls(sections: readonly Section[]): string[] {
    const asked = new Set<string>();
    for (const section of sections) {
      if (this.locked(section)) continue;
      REROLLS[section].forEach((s) => asked.add(s));
      if (section === 'background' && !this.locked('biography')) {
        REROLLS.biography.forEach((s) => asked.add(s));
      }
    }
    return ORDER.filter((s) => asked.has(s));
  }

  unlocked(): Section[] {
    return SECTIONS.filter((section) => !this.locked(section));
  }

  character(): Character {
    if (!this.written) throw new Error('The character hasn’t been written yet');
    return clone(this.work) as Character;
  }

  apply(written: Written, rerolled?: readonly string[]): void {
    const before = this.work.values;
    this.work = clone(written.character);
    if (canonical(before) !== canonical(this.work.values)) {
      this.values = ValueModel.fit(written.character.values);
    }
    if (!rerolled || rerolled.some((s) => CRITIQUED.has(s))) {
      this.suggestions = written.suggestions;
      this.notes = written.notes;
    }
    this.warnings = written.warnings;
  }

  markSaved(character: Character): void {
    this.saved = clone(character);
    this.work = clone(character);
  }

  /** A design pick leaves `voice.description` alone, so it's passed here to save. */
  markVoice(character: Character, description?: string): void {
    this.saved = clone(character);
    const kept = description ?? this.work.voice?.description ?? character.voice.description;
    this.work.voice = { ...character.voice, description: kept };
    for (const field of SERVER_SET) Object.assign(this.work, { [field]: character[field] });
  }

  accept(suggestion: Suggestion): void {
    const match = /^(\w+)(?:\[(\d+)\])?$/.exec(suggestion.field);
    if (match) {
      const [, field, index] = match;
      const text = suggestion.suggested;
      if (field === 'past' && index !== undefined && this.work.past?.[+index]) {
        this.work.past[+index] = { ...this.work.past[+index], content: text };
      } else if (field === 'hooks' && index !== undefined && this.work.hooks?.[+index]) {
        this.work.hooks[+index] = { ...this.work.hooks[+index], description: text };
      } else if (field === 'interests') {
        this.work.interests = text
          .split(';')
          .map((s) => s.trim())
          .filter(Boolean);
      } else if (field === 'backstory' || field === 'persona' || field === 'speaking_style') {
        this.work[field] = text;
      }
      this.locks.add('biography');
    }
    this.ignore(suggestion);
  }

  ignore(suggestion: Suggestion): void {
    this.suggestions = this.suggestions.filter((s) => s !== suggestion);
  }

  problems(year: number = new Date().getUTCFullYear()): string[] {
    const w = this.work;
    if (!this.written) return ['Write the character first.'];
    const problems: string[] = [];
    const blank = (text: string | undefined) => !text?.trim();
    if (blank(w.name)) problems.push('Give them a name.');
    const age =
      w.birth_year === undefined || Number.isNaN(w.birth_year) ? NaN : year - w.birth_year;
    if (!(age >= 0 && age <= 120)) problems.push('Their birth year has to make them 0 to 120.');
    if (blank(w.origin)) problems.push('Say where they’re from.');
    if (blank(w.occupation)) problems.push('Give them an occupation.');
    if (w.arrival) {
      if (blank(w.arrival.reason)) problems.push('Say why they came.');
      if (w.arrival.age > age)
        problems.push(`They arrived at ${w.arrival.age}, but they’re ${age}.`);
    }
    if (blank(w.backstory)) problems.push('The backstory is empty.');
    if (blank(w.persona)) problems.push('The persona is empty.');
    if (blank(w.speaking_style)) problems.push('The speaking style is empty.');
    const mannerisms = w.mannerisms ?? [];
    if (mannerisms.length > MAX_MANNERISMS)
      problems.push(`Keep to ${MAX_MANNERISMS} verbal habits at most.`);
    mannerisms.forEach((mannerism, i) => {
      if (mannerism.length > MANNERISM_LENGTH)
        problems.push(`Verbal habit ${i + 1} is over ${MANNERISM_LENGTH} characters.`);
    });
    (w.past ?? []).forEach((memory, i) => {
      if (blank(memory.content)) problems.push(`Life event ${i + 1} is empty.`);
      if (memory.age > age) {
        problems.push(`Life event ${i + 1} happened at ${memory.age}, but they’re ${age}.`);
      }
    });
    (w.hooks ?? []).forEach((hook, i) => {
      if (blank(hook.description)) problems.push(`Tie ${i + 1} is empty.`);
    });
    if (w.craft && blank(w.craft.form)) problems.push('Say what they make, or choose nothing.');
    if (CORE_VALUES.some((v) => !(v in (w.values ?? {}))))
      problems.push('Some values are missing.');
    return problems;
  }
}

export function clone<T>(value: T): T {
  return structuredClone(value);
}

function editable(work: Work): Work {
  const copy = { ...work };
  for (const field of SERVER_SET) delete copy[field];
  return copy;
}

function canonical(value: unknown): string {
  return JSON.stringify(value, (_, v) =>
    v && typeof v === 'object' && !Array.isArray(v)
      ? Object.fromEntries(Object.entries(v).sort(([a], [b]) => a.localeCompare(b)))
      : v,
  );
}
