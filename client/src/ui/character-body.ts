import type { Bionic, BodyPart } from '../net';
import type { BodyRow } from './character-panel';

/** Where each part sits on `character-body.svg`, in its 200 × 240 units: its middle, width and height. */
export const PLACES: Record<BodyPart, { x: number; y: number; w: number; h: number; flip?: boolean }> = {
  right_eye: { x: 91, y: 41, w: 15, h: 15 },
  left_eye: { x: 109, y: 41, w: 15, h: 15 },
  vertebra: { x: 100, y: 80, w: 14, h: 26 },
  stomach: { x: 111, y: 104, w: 24, h: 22 },
  right_kidney: { x: 88, y: 124, w: 16, h: 18 },
  left_kidney: { x: 112, y: 124, w: 16, h: 18, flip: true },
  legs: { x: 100, y: 172, w: 40, h: 56 },
  feet: { x: 100, y: 213, w: 44, h: 22 },
};
export const CHART = { width: 200, height: 240 };

const ORGANS: Record<BodyPart, string> = {
  left_eye: 'eye',
  right_eye: 'eye',
  vertebra: 'vertebra',
  stomach: 'stomach',
  left_kidney: 'kidney',
  right_kidney: 'kidney',
  legs: 'legs',
  feet: 'feet',
};

const STAGE_1_LEGS = 'hydraulic_legs';

/** Each bionic's picture: its line's, so every grade looks alike, and stage 1's legs as the hydraulic legs. */
export const PICTURES: Record<Bionic, string> = {
  hydraulic_legs: STAGE_1_LEGS,
  spring_legs: STAGE_1_LEGS,
  sprint_legs: STAGE_1_LEGS,
  blade_legs: STAGE_1_LEGS,
  premium_legs: STAGE_1_LEGS,
  datajack: 'datajack',
  infrared_eye: 'infrared_eye',
  power_cell: 'power_cell',
  power_cell_2: 'power_cell',
  power_cell_3: 'power_cell',
  bionic_legs: 'bionic_legs',
  bionic_legs_2: 'bionic_legs',
  bionic_legs_3: 'bionic_legs',
  spring_feet: 'spring_feet',
  spring_feet_2: 'spring_feet',
};

const GRADES: Partial<Record<Bionic, [number, number]>> = {
  power_cell: [1, 3],
  power_cell_2: [2, 3],
  power_cell_3: [3, 3],
  bionic_legs: [1, 3],
  bionic_legs_2: [2, 3],
  bionic_legs_3: [3, 3],
  spring_feet: [1, 2],
  spring_feet_2: [2, 2],
};

const runs = (count: number) =>
  `Runs ${count} other bionics. You never eat: hunger is power now, which drains faster with each bionic and charges at plugs.`;

const DOES: Record<Bionic, string> = {
  power_cell: runs(3),
  power_cell_2: runs(4),
  power_cell_3: runs(5),
  datajack: 'Plugs you into terminals, old machinery and the lift down to the sewers.',
  infrared_eye: 'Sees in the dark without the lamp, and sees a liar’s flush.',
  bionic_legs: 'Run faster, jump further and kick harder.',
  bionic_legs_2: 'Run faster, jump further and kick harder than the first grade.',
  bionic_legs_3: 'The fastest run, the furthest jump and the hardest kick.',
  spring_feet: 'Jump higher, onto ledges you couldn’t reach.',
  spring_feet_2: 'Jump higher still.',
  hydraulic_legs: 'Jump higher.',
  spring_legs: 'Jump higher still.',
  sprint_legs: 'Run faster, and jump further.',
  blade_legs: 'Run faster still.',
  premium_legs: 'Run faster and jump higher.',
};

const OWN: Record<BodyPart, string> = {
  left_eye: 'One of your own eyes.',
  right_eye: 'One of your own eyes.',
  vertebra: 'A bone of your own spine. A datajack could go in its place.',
  stomach: 'Your own stomach, so you eat. A power cell could go in its place, and you’d never eat again.',
  left_kidney: 'One of your own kidneys. You can live on one.',
  right_kidney: 'One of your own kidneys. You can live on one.',
  legs: 'Your own legs.',
  feet: 'Your own feet.',
};

/** The picture at a part's place: their own organ, its stitched socket once sold, or the bionic fitted there. */
export function pictureOf({ part, state, fitted }: Pick<BodyRow, 'part' | 'state' | 'fitted'>): string {
  if (state === 'sold') return `${ORGANS[part]}_sold`;
  if (state === 'bionic' && fitted) return PICTURES[fitted];
  return ORGANS[part];
}

export function gradeOf(bionic: Bionic | undefined): [number, number] | undefined {
  return bionic && GRADES[bionic];
}

export type PartDetails = { title: string; state: BodyRow['state']; status: string; lines: string[] };

/** What hovering over a part, or picking it with Up and Down, says about it. */
export function partDetails({ part, label, state, text, fitted }: BodyRow): PartDetails {
  if (state === 'sold') {
    return { title: label, state, status: 'Sold', lines: ['Stitched shut where it was.'] };
  }
  if (state === 'present' || !fitted) return { title: label, state, status: 'Your own', lines: [OWN[part]] };
  const grade = gradeOf(fitted);
  return {
    title: label,
    state,
    status: text,
    lines: [
      `A bionic in place of your ${label.toLowerCase()}${grade ? `, grade ${grade[0]} of ${grade[1]}` : ''}.`,
      DOES[fitted],
    ],
  };
}
