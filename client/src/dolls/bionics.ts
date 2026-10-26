import type { Bionic, Body } from '../net/protocol';

export const PLAYER_FIGURE = 'player';
type Shown = Extract<Bionic, 'bionic_legs' | 'spring_feet' | 'datajack' | 'infrared_eye'>;
/** In the order a figure's id names them. */
export const FITTED: readonly Shown[] = ['bionic_legs', 'spring_feet', 'datajack', 'infrared_eye'];
const NAMES: Record<Shown, string> = {
  bionic_legs: 'bionic_legs',
  spring_feet: 'feet',
  datajack: 'datajack',
  infrared_eye: 'eye',
};
/** The part a figure shows for each bionic: every grade of a line alike. */
const SHOWN_AS: Record<Bionic, Shown | undefined> = {
  power_cell: undefined,
  power_cell_2: undefined,
  power_cell_3: undefined,
  bionic_legs: 'bionic_legs',
  bionic_legs_2: 'bionic_legs',
  bionic_legs_3: 'bionic_legs',
  spring_feet: 'spring_feet',
  spring_feet_2: 'spring_feet',
  datajack: 'datajack',
  infrared_eye: 'infrared_eye',
};

/** The bionics a body's figure shows, in `FITTED`'s order. */
export function fitted(body?: Body): Shown[] {
  const parts = new Set<Shown>();
  for (const part of Object.values(body ?? {})) {
    const shown = SHOWN_AS[part as Bionic];
    if (shown) parts.add(shown);
  }
  return FITTED.filter((bionic) => parts.has(bionic));
}

/** The player's figure for a body: `player` with nothing fitted, `player_bionic_legs_feet_eye` and so on. */
export const playerFigureId = (body?: Body): string =>
  [PLAYER_FIGURE, ...fitted(body).map((bionic) => NAMES[bionic])].join('_');

export const isPlayerFigure = (id?: string): boolean =>
  id === PLAYER_FIGURE || !!id?.startsWith(`${PLAYER_FIGURE}_`);

/** The player's body as last heard, and who to tell when what's fitted changes. */
export class PlayerBody {
  private body?: Body;
  private readonly listeners = new Set<(figure: string) => void>();

  get figure(): string {
    return playerFigureId(this.body);
  }

  set(body: Body): void {
    const before = this.figure;
    this.body = body;
    if (this.figure !== before) this.listeners.forEach((listener) => listener(this.figure));
  }

  /** Calls `listener` with the new figure's id whenever it changes. */
  onChange(listener: (figure: string) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}
