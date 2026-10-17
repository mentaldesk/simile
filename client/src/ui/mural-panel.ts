import type { Position, Wall } from '../net';
import { muralView, wallNear, type MuralView, type MuralWalls } from '../world/iso/murals';
import type { Point } from '../world/view';
import { pressedNewsKey } from './keys';
import './mural-panel.css';
import { NEWS_KEY } from './tuning';

const KEY = NEWS_KEY.toUpperCase();

/** How far the player can walk from where they opened a mural's panel, out of its wall's reach. */
const STAY_TILES = 1;

/** A mural up close: its picture, title, artist and statement. */
export class MuralPanel {
  readonly hint: HTMLElement;
  private readonly panel: HTMLElement;
  private readonly title: HTMLElement;
  private readonly image: HTMLImageElement;
  private readonly artist: HTMLElement;
  private readonly statement: HTMLElement;
  private readonly walls: MuralWalls;
  private readonly view: () => MuralView | undefined;
  private shown?: { wall: string; from?: Position };
  readonly stop: () => void;

  constructor(
    parent: HTMLElement,
    walls: MuralWalls,
    view: () => MuralView | undefined = muralView,
  ) {
    this.walls = walls;
    this.view = view;
    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'mural-hint';
    this.hint.hidden = true;
    this.panel = parent.appendChild(document.createElement('section'));
    this.panel.className = 'mural';
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    this.panel.ariaLabel = 'Mural';
    const header = this.panel.appendChild(document.createElement('header'));
    this.title = header.appendChild(document.createElement('b'));
    header.appendChild(document.createElement('span')).textContent = `Esc or ${KEY} close`;
    const body = this.panel.appendChild(document.createElement('div'));
    this.image = body.appendChild(document.createElement('img'));
    const words = body.appendChild(document.createElement('div'));
    this.artist = words.appendChild(document.createElement('small'));
    this.statement = words.appendChild(document.createElement('p'));

    this.panel.addEventListener('keydown', (event) => {
      event.stopPropagation();
      if (event.key === 'Escape' || pressedNewsKey(event)) {
        event.preventDefault();
        this.close();
      }
    });
    this.stop = walls.onChange(() => {
      if (this.shown) this.render(this.shown.wall);
    });
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  /** The painted wall the player stands near, while murals are drawn. */
  near(position: Position | undefined): Wall | undefined {
    return this.view() ? wallNear(this.walls.walls, position) : undefined;
  }

  look(position: Position | undefined): boolean {
    const wall = this.near(position);
    if (wall) this.open(wall.id, position);
    return wall !== undefined;
  }

  /** Opens the mural at a point on the game canvas, if there is one. */
  click(point: Point, position: Position | undefined): boolean {
    const wall = this.view()?.wallAt(point);
    if (wall) this.open(wall, position);
    return wall !== undefined;
  }

  open(wallId: string, from?: Position): void {
    this.shown = { wall: wallId, from };
    if (!this.render(wallId)) return;
    this.panel.hidden = false;
    this.hint.hidden = true;
    this.panel.focus();
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
    this.shown = undefined;
  }

  /** Each frame: closes the panel once the player walks off, and hints at a mural nearby. */
  update(position: Position | undefined, hint = true): void {
    if (this.shown && !this.stays(this.shown, position)) this.close();
    const near = this.near(position);
    this.hint.hidden = !hint || this.isOpen || !near;
    if (near?.mural) this.hint.textContent = `Press ${KEY} to look at “${near.mural.title}”.`;
  }

  private stays({ wall, from }: { wall: string; from?: Position }, position: Position | undefined) {
    if (!this.view() || !position) return false;
    if (this.near(position)?.id === wall) return true;
    return from !== undefined && Math.hypot(position.x - from.x, position.y - from.y) <= STAY_TILES;
  }

  private render(wallId: string): boolean {
    const mural = this.walls.wall(wallId)?.mural;
    if (!mural) {
      this.close();
      return false;
    }
    this.title.textContent = mural.title;
    if (this.image.getAttribute('src') !== mural.image) this.image.src = mural.image;
    this.image.alt = mural.title;
    this.artist.textContent = `by ${mural.artist.name}`;
    this.statement.textContent = mural.statement;
    return true;
  }
}
