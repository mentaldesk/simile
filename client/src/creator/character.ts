// Generated from server/simile/schema/json/Character.json by character.test.ts.
// Don't edit it by hand: run `npx vitest run src/creator/character.test.ts -u` in client/.

export type Id = string;
export type Name = string;
export type BirthYear = number;
export type Gender = 'woman' | 'man' | 'nonbinary';
/**
 * Where they were born, or for someone born in the village where their family is from, e.g. "Vietnam".
 */
export type Origin = string;
export type Age = number;
/**
 * Why they came, e.g. "for a job".
 */
export type Reason = string;
export type Occupation = string;
/**
 * Their whole life in prose, for the debug UI and for assets.
 */
export type Backstory = string;
export type Persona = string;
export type SpeakingStyle = string;
/**
 * Up to 3 habits that show in how they talk, e.g. "answers a question with another question". Left out when empty.
 *
 * @maxItems 3
 */
export type Mannerisms = [] | [string] | [string, string] | [string, string, string];
export type Interests = string[];
/**
 * How old they were when it happened.
 */
export type Age1 = number;
/**
 * The memory in their own words, ready for a prompt.
 */
export type Content = string;
/**
 * How much it matters to them, 0-1.
 */
export type Salience = number;
/**
 * How they feel about it, from -1 to 1.
 */
export type Valence = number;
export type Past = PastMemory[];
/**
 * Mutual: `estranged_sibling`, `ex_partner`, `old_friend`, `rival`. One-way, where the actor
 * did it to the target: `debt`, the actor borrowed money from the target and still owes it;
 * `secret`, the target saw the actor do something the actor wants kept hidden; `betrayal`, the
 * actor betrayed the target; `saved_life`, the actor saved the target's life.
 */
export type HookKind =
  | 'estranged_sibling'
  | 'ex_partner'
  | 'old_friend'
  | 'rival'
  | 'debt'
  | 'secret'
  | 'betrayal'
  | 'saved_life';
/**
 * `mutual` for a mutual kind, else `actor` or `target`.
 */
export type HookSide = 'mutual' | 'actor' | 'target';
/**
 * The tie from this character's side in a sentence, without naming the other resident.
 */
export type Description = string;
export type Hooks = Hook[];
/**
 * How often they start a conversation and how long they stay.
 */
export type Sociability = number;
/**
 * How much more a bad turn weighs with them than a good one.
 */
export type NegativityBias = number;
/**
 * How fast a grudge fades.
 */
export type Forgiveness = number;
/**
 * How far a first meeting swings their opinion of someone.
 */
export type FirstImpressions = number;
export type Skin = string;
export type HairStyle = 'bald' | 'buzz' | 'short' | 'curly' | 'bob' | 'long' | 'ponytail' | 'bun';
export type HairColour = string;
export type TopColour = string;
export type BottomColour = string;
export type ShoeColour = string;
export type Build = 'slim' | 'average' | 'broad';
export type Accessory =
  'glasses' | 'sunglasses' | 'cap' | 'beanie' | 'headphones' | 'scarf' | 'backpack' | 'apron';
export type Accessories = Accessory[];
/**
 * What the voice sounds like, for the voice design model.
 */
export type Description1 = string;
/**
 * A neutral line in character, 5-10 seconds of speech. The clip's transcript.
 */
export type ReferenceLine = string;
/**
 * The recorded reference clip, relative to the repository root. Null until the voice is designed.
 */
export type ReferenceClip = string | null;
/**
 * True when VoiceDesign can't do the accent, so the clip has to be recorded.
 */
export type NeedsRecording = boolean;
export type Medium = 'writing' | 'mural' | 'painting';
/**
 * What they make, in a few words, e.g. "short poems about the river".
 */
export type Form = string;
/**
 * `premade` characters ship with the game and are read-only; `player` ones a player made.
 */
export type CharacterSource = 'premade' | 'player';
export type Created = string;
export type Updated = string;
/**
 * Goes up by one on every edit.
 */
export type Version = number;

/**
 * A character in the library, apart from any village. Casting makes an Npc from it.
 */
export interface Character {
  id: Id;
  name: Name;
  birth_year: BirthYear;
  gender: Gender;
  origin: Origin;
  /**
   * Null if they were born in the village.
   */
  arrival: Arrival | null;
  occupation: Occupation;
  values: Values;
  backstory: Backstory;
  persona: Persona;
  speaking_style: SpeakingStyle;
  mannerisms?: Mannerisms;
  interests: Interests;
  past: Past;
  hooks: Hooks;
  traits: Traits;
  appearance: Appearance;
  voice: CharacterVoice;
  /**
   * Null if they don't make anything.
   */
  craft: Craft | null;
  source: CharacterSource;
  created: Created;
  updated: Updated;
  version: Version;
}
/**
 * When and why a character came to the village.
 */
export interface Arrival {
  age: Age;
  reason: Reason;
}
/**
 * How much they care about each of the 24 core values, 0-1. All are present.
 */
export interface Values {
  [k: string]: number;
}
/**
 * A memory of their life before the game, which casting turns into a `past` Memory.
 */
export interface PastMemory {
  age: Age1;
  content: Content;
  salience: Salience;
  valence: Valence;
}
/**
 * An open tie to another resident, which casting binds to someone in the cast.
 */
export interface Hook {
  kind: HookKind;
  side: HookSide;
  description: Description;
}
/**
 * The numbers social/ and behaviour/ read. Each is 0-1, and 0.5 is how residents behave
 * without traits.
 */
export interface Traits {
  sociability: Sociability;
  negativity_bias: NegativityBias;
  forgiveness: Forgiveness;
  first_impressions: FirstImpressions;
}
/**
 * What a character looks like, for the sprite generator. Colours are #rrggbb.
 */
export interface Appearance {
  skin: Skin;
  hair_style: HairStyle;
  hair_colour: HairColour;
  top_colour: TopColour;
  bottom_colour: BottomColour;
  shoe_colour: ShoeColour;
  build: Build;
  accessories: Accessories;
}
export interface CharacterVoice {
  description: Description1;
  reference_line: ReferenceLine;
  reference_clip: ReferenceClip;
  needs_recording: NeedsRecording;
}
/**
 * What a resident makes in their own time, which can differ from their job.
 */
export interface Craft {
  medium: Medium;
  form: Form;
}
