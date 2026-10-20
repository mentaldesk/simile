import type { Position, Wall } from '../net';
import {
  MURAL_REACH_TILES,
  muralView,
  wallNear,
  type MuralView,
  type MuralWalls,
} from '../world/iso/murals';
import { mapOf, VILLAGE } from '../world/map';
import type { Point } from '../world/view';
import { pressedNewsKey } from './keys';
import './mural-panel.css';
import { sideView, tilesApart } from './side-view';
import { NEWS_KEY } from './tuning';

const KEY = NEWS_KEY.toUpperCase();

/** How far the player can walk from where they opened a mural's panel, out of its wall's reach. */
const STAY_TILES = 1;

/** On a side-view map every wall faces the camera, so its reach runs along x from its ends. */
function wallAlong(walls: readonly Wall[], position: Position): Wall | undefined {
  const along = position.x + 0.5;
  let nearest: { wall: Wall; distance: number } | undefined;
  for (const wall of walls) {
    if (!wall.mural || (wall.map ?? VILLAGE) !== mapOf(position)) continue;
    const distance = Math.max(wall.x - along, 0, along - (wall.x + wall.width));
    if (distance > MURAL_REACH_TILES) continue;
    if (!nearest || distance < nearest.distance) nearest = { wall, distance };
  }
  return nearest?.wall;
}

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
  private hinted?: string;
  readonly stop: () => void;

  constructor(
    parent: HTMLElement,
    walls: MuralWalls,
    view: () => MuralView | undefined = muralView,
  ) {
    this.walls = walls;
    this.view = view;
    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'news-hint';
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
    if (!this.view() || !position) return undefined;
    const walls = this.walls.walls;
    return sideView(mapOf(position)) ? wallAlong(walls, position) : wallNear(walls, position);
  }

  look(position: Position | undefined): boolean {
    const wall = this.near(position);
    if (wall) this.open(wall.id, position);
    return wall !== undefined;
  }

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
    const mural = this.near(position)?.mural;
    this.hint.hidden = !hint || this.isOpen || !mural;
    if (mural && mural.work_id !== this.hinted) {
      this.hinted = mural.work_id;
      this.hint.textContent = `Press ${KEY} to look at “${mural.title}”.`;
    }
  }

  private stays({ wall, from }: { wall: string; from?: Position }, position: Position | undefined) {
    if (!this.view() || !position) return false;
    if (this.near(position)?.id === wall) return true;
    const moved = from && tilesApart(from, position);
    return moved !== undefined && moved <= STAY_TILES;
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
