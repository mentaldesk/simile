import type { Bionic, Body } from '../net/protocol';

export const PLAYER_FIGURE = 'player';
type Shown = Extract<Bionic, 'hydraulic_legs' | 'datajack' | 'infrared_eye'>;
/** In the order a figure's id names them. */
export const FITTED: readonly Shown[] = ['hydraulic_legs', 'datajack', 'infrared_eye'];
const NAMES: Record<Shown, string> = { hydraulic_legs: 'legs', datajack: 'datajack', infrared_eye: 'eye' };
/** Every grade of legs, which a figure shows alike. */
export const LEGS: ReadonlySet<string> = new Set<Bionic>(['hydraulic_legs', 'spring_legs', 'sprint_legs', 'blade_legs', 'premium_legs']);

/** The bionics a body's figure shows, in `FITTED`'s order, any grade of legs as the hydraulic legs. */
export function fitted(body?: Body): Shown[] {
  const parts = new Set<string>(Object.values(body ?? {}).map((part: string) => (LEGS.has(part) ? 'hydraulic_legs' : part)));
  return FITTED.filter((bionic) => parts.has(bionic));
}

/** The player's figure for a body: `player` with nothing fitted, `player_legs_eye` and so on. */
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
