import type Phaser from 'phaser';
import type { FigureManifest } from '../dolls/manifest';
import type { DollPose } from '../dolls/rig';
import type { ClientMessage, Facing, Item, ReloadMessage, SideFacing } from '../net';
import { DEPTH } from './depths';
import { FIRE_KEY, RELOAD_KEY } from './input';
import { feetOf, PPM, xOf } from './layout';
import type { MapPosition } from './player';
import type { MoveReport } from './report';

/** Up and down don't turn the gun, so it stays the last way they faced sideways. */
export const sideOf = (facing: Facing, last: SideFacing): SideFacing =>
  facing === 'east' || facing === 'west' ? facing : last;

const isUsable = ({ kind, condition }: Item) => kind === 'weapon' && !!condition;
const hasRoom = ({ rounds, capacity }: Item) => (rounds ?? 0) < (capacity ?? 0);
const isLoaded = (item: Item) => isUsable(item) && !!item.rounds;

/** The rounds they carry for `weapon`. */
const spare = (items: readonly Item[], weapon: Item) =>
  items.filter(({ kind, material }) => kind === 'rounds' && material === weapon.material).reduce((sum, { amount }) => sum + (amount ?? 1), 0);

/** Whether a press of fire goes: not through a door, on a ladder, stairs or the lift, or in bed. */
export const canFire = ({ passing, climbing, bed }: { passing: boolean; climbing: unknown; bed: number }): boolean =>
  !passing && !climbing && bed === 0;

/** The weapon fire would use: the first loaded, else the first to reload, else any. */
export const firesNext = (items: readonly Item[] | undefined): Item | undefined =>
  items?.find(isLoaded) ?? items?.find(isUsable) ?? items?.find(({ kind }) => kind === 'weapon');

/** What a press of fire sends, in order: the server shoots from where it last kept them, so a move the throttle is holding back goes first. */
export function firing(
  moves: Pick<MoveReport, 'forget' | 'next'>,
  position: MapPosition,
  now: number,
  items: readonly Item[] | undefined,
  facing: SideFacing,
): ClientMessage[] {
  if (!items?.some(isLoaded)) return [];
  moves.forget();
  const move = moves.next(position, now);
  return [...(move ? [{ type: 'player_move', position: move } as const] : []), { type: 'fire', facing }];
}

/** What a press of reload sends, as the server would take it. */
export function reloading(items: readonly Item[] | undefined): ReloadMessage | undefined {
  const weapon = items?.find((item) => isUsable(item) && hasRoom(item));
  return weapon && spare(items!, weapon) > 0 ? { type: 'reload' } : undefined;
}

/** The rounds and condition of the weapon fire would use. */
export function weaponLine(items: readonly Item[] | undefined): string | undefined {
  const weapon = firesNext(items);
  if (!weapon) return undefined;
  if (!isUsable(weapon)) return `${weapon.name}: worn out`;
  const left = spare(items!, weapon);
  const hint = !weapon.rounds && left ? `, ${RELOAD_KEY} reloads` : '';
  return `${FIRE_KEY}  ${weapon.name}: ${weapon.rounds}/${weapon.capacity}, ${left} spare, ${Math.round(weapon.condition! * 100)}% condition${hint}`;
}

const GUN_SECONDS = 0.35;
const FLASH_SECONDS = 0.08;
/** Above the feet, for a figure with no aim painted. */
const HAND_M = 1.2;
const REACH_M = 0.35;
const LINE_PX = { x: 12, bottom: 16, font: 15 };

/** Metres ahead of and above the feet, from the frame's `muzzle`. */
export function muzzleOf(figure: FigureManifest | undefined): { ahead: number; up: number } {
  const aim = figure?.frames.aim;
  if (!figure || !aim?.muzzle) return { ahead: REACH_M, up: HAND_M };
  return { ahead: (aim.muzzle[0] - aim.feet[0]) / figure.ppm, up: (aim.feet[1] - aim.muzzle[1]) / figure.ppm };
}

/** Where the flash starts: the end of the pistol the way they face. */
export function shotAt(at: { x: number; y: number }, facing: SideFacing, figure?: FigureManifest): { x: number; y: number; way: number } {
  const way = facing === 'east' ? 1 : -1;
  const { ahead, up } = muzzleOf(figure);
  return { x: xOf(at.x) + way * ahead * PPM, y: feetOf(at.y) - up * PPM, way };
}

/** They aim from these for a moment after a shot; in anything else they couldn't have fired. */
const AIMS_FROM = new Set<DollPose>(['standing', 'walking', 'jumping', 'landing']);

/** The flash for a moment after each shot, over the darkness since a flash lights itself, the figure aiming a little longer, and the weapon's line in a corner. */
export class ShotView {
  private readonly scene: Phaser.Scene;
  private readonly line: Phaser.GameObjects.Text;
  private flash?: Phaser.GameObjects.Image;
  private since = Infinity;

  constructor(scene: Phaser.Scene) {
    this.scene = scene;
    this.line = scene.add.text(0, 0, '', { fontFamily: 'monospace', fontSize: `${LINE_PX.font}px`, color: '#e8ecf4', backgroundColor: '#05070ea0', padding: { x: 6, y: 3 } });
    this.line.setOrigin(0, 1).setDepth(DEPTH.fade - 1).setVisible(false);
  }

  /** `texture` is the flash, once it's loaded. */
  setFlash(texture: string): void {
    this.flash = this.scene.add.image(0, 0, texture).setDepth(DEPTH.dark + 1).setVisible(false);
  }

  fired(): void {
    this.since = 0;
  }

  /** For the dev harness. */
  drawn(): { gun: boolean; flash: boolean; line: string | null } {
    return { gun: this.since < GUN_SECONDS, flash: this.since < FLASH_SECONDS, line: this.line.visible ? this.line.text : null };
  }

  /** How the player is drawn: aiming the way they face now, for a moment after a shot. */
  pose<T extends { pose: DollPose; facing: Facing }>(drawn: T, facing: SideFacing): T {
    return this.since < GUN_SECONDS && AIMS_FROM.has(drawn.pose) ? { ...drawn, pose: 'aiming', facing } : drawn;
  }

  /** `at` is the player in street cells, while they're shown, as `figure`. */
  update(dt: number, at: { x: number; y: number } | undefined, facing: SideFacing, line: string | undefined, view: Phaser.Geom.Rectangle, zoom: number, figure: FigureManifest | undefined): void {
    this.since += dt;
    this.drawFlash(at, facing, figure);
    this.line.setVisible(!!line);
    if (!line) return;
    const scale = 1 / zoom;
    if (this.line.text !== line) this.line.setText(line);
    this.line.setScale(scale).setPosition(view.x + LINE_PX.x * scale, view.bottom - LINE_PX.bottom * scale);
  }

  destroy(): void {
    this.flash?.destroy();
    this.line.destroy();
  }

  private drawFlash(at: { x: number; y: number } | undefined, facing: SideFacing, figure: FigureManifest | undefined): void {
    const { flash } = this;
    if (!flash) return;
    const shown = !!at && this.since < FLASH_SECONDS;
    flash.setVisible(shown);
    if (!at || !shown) return;
    const { x, y, way } = shotAt(at, facing, figure);
    flash.setPosition(x, y).setOrigin(way > 0 ? 0 : 1, 0.5).setFlipX(way < 0);
  }
}
