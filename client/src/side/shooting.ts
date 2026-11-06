import type Phaser from 'phaser';
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

/** The weapon's rounds and condition, for the one fire would use: the first loaded, else the first to reload, else any. */
export function weaponLine(items: readonly Item[] | undefined): string | undefined {
  const weapon = items?.find(isLoaded) ?? items?.find(isUsable) ?? items?.find(({ kind }) => kind === 'weapon');
  if (!weapon) return undefined;
  if (!isUsable(weapon)) return `${weapon.name}: worn out`;
  const left = spare(items!, weapon);
  const hint = !weapon.rounds && left ? `, ${RELOAD_KEY} reloads` : '';
  return `${FIRE_KEY}  ${weapon.name}: ${weapon.rounds}/${weapon.capacity}, ${left} spare, ${Math.round(weapon.condition! * 100)}% condition${hint}`;
}

const GUN_SECONDS = 0.35;
const FLASH_SECONDS = 0.08;
/** Above the feet, the player's hand at the end of their arm. */
const HAND_M = 1.2;
const REACH_M = 0.35;
const GUN_M = { length: 0.3, height: 0.1 };
const FLASH_M = 0.22;
const GUN_COLOUR = 0x2b2e36;
const FLASH_COLOURS = [0xffb33a, 0xfff2b0];
const LINE_PX = { x: 12, bottom: 16, font: 15 };

/** Where the flash and the pistol are drawn: the placeholder until Q13 paints them. */
export function shotAt(at: { x: number; y: number }, facing: SideFacing): { x: number; y: number; way: number } {
  const way = facing === 'east' ? 1 : -1;
  return { x: xOf(at.x) + way * REACH_M * PPM, y: feetOf(at.y) - HAND_M * PPM, way };
}

/** A plain pistol and flash for a moment after each shot, over the darkness since a flash lights itself, and the weapon's line in a corner. */
export class ShotView {
  private readonly graphics: Phaser.GameObjects.Graphics;
  private readonly line: Phaser.GameObjects.Text;
  private since = Infinity;

  constructor(scene: Phaser.Scene) {
    this.graphics = scene.add.graphics().setDepth(DEPTH.dark + 1);
    this.line = scene.add.text(0, 0, '', { fontFamily: 'monospace', fontSize: `${LINE_PX.font}px`, color: '#e8ecf4', backgroundColor: '#05070ea0', padding: { x: 6, y: 3 } });
    this.line.setOrigin(0, 1).setDepth(DEPTH.fade - 1).setVisible(false);
  }

  fired(): void {
    this.since = 0;
  }

  /** `at` is the player in street cells, while they're shown. */
  update(dt: number, at: { x: number; y: number } | undefined, facing: SideFacing, line: string | undefined, view: Phaser.Geom.Rectangle, zoom: number): void {
    this.since += dt;
    this.graphics.clear();
    if (at && this.since < GUN_SECONDS) this.draw(shotAt(at, facing));
    this.line.setVisible(!!line);
    if (!line) return;
    const scale = 1 / zoom;
    if (this.line.text !== line) this.line.setText(line);
    this.line.setScale(scale).setPosition(view.x + LINE_PX.x * scale, view.bottom - LINE_PX.bottom * scale);
  }

  destroy(): void {
    this.graphics.destroy();
    this.line.destroy();
  }

  private draw({ x, y, way }: { x: number; y: number; way: number }): void {
    const { graphics } = this;
    const length = GUN_M.length * PPM;
    const height = GUN_M.height * PPM;
    graphics.fillStyle(GUN_COLOUR).fillRect(way > 0 ? x : x - length, y - height / 2, length, height);
    if (this.since >= FLASH_SECONDS) return;
    const muzzle = x + way * length;
    FLASH_COLOURS.forEach((colour, i) => {
      const radius = (FLASH_M * PPM) / (i + 1);
      graphics.fillStyle(colour).fillCircle(muzzle + way * radius * 0.6, y, radius);
    });
  }
}
