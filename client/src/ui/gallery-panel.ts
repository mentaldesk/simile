import type { Frame, Painting, Position } from '../net';
import type { Interactable } from '../world/interactables';
import type { GalleryFrames } from '../world/paintings';
import { mapOf } from '../world/map';
import { callCue } from './call-cue';
import './gallery-panel.css';
import { pressedNewsKey } from './keys';
import { NEWS_KEY } from './tuning';

const KEY = NEWS_KEY.toUpperCase();

/** `interactableAt` in the game. */
type Find = (map: string, position: Position | undefined) => Interactable | undefined;

/** A painting up close, opened with E at its frame in the gallery. */
export class GalleryPanel {
  readonly hint: HTMLElement;
  private readonly panel: HTMLElement;
  private readonly title: HTMLElement;
  private readonly image: HTMLImageElement;
  private readonly artist: HTMLElement;
  private readonly statement: HTMLElement;
  private readonly frames: GalleryFrames;
  private readonly find: Find;
  private shown?: { map: string; id: string };
  readonly stop: () => void;

  constructor(parent: HTMLElement, frames: GalleryFrames, find: Find) {
    this.frames = frames;
    this.find = find;
    this.hint = parent.appendChild(document.createElement('div'));
    this.hint.className = 'news-hint';
    this.hint.hidden = true;
    this.panel = parent.appendChild(document.createElement('section'));
    this.panel.className = 'gallery';
    this.panel.tabIndex = -1;
    this.panel.hidden = true;
    this.panel.ariaLabel = 'Painting';
    callCue.slot(this.panel);
    const header = this.panel.appendChild(document.createElement('header'));
    this.title = header.appendChild(document.createElement('b'));
    header.appendChild(document.createElement('span')).textContent = `Esc or ${KEY} close`;
    this.image = this.panel.appendChild(document.createElement('img'));
    const words = this.panel.appendChild(document.createElement('div'));
    this.artist = words.appendChild(document.createElement('small'));
    this.statement = words.appendChild(document.createElement('p'));

    this.panel.addEventListener('keydown', (event) => {
      event.stopPropagation();
      if (event.key === 'Escape' || pressedNewsKey(event)) {
        event.preventDefault();
        this.close();
      }
    });
    this.stop = frames.onChange(() => {
      if (this.shown) this.render(this.shown);
    });
  }

  get isOpen(): boolean {
    return !this.panel.hidden;
  }

  /** The frame whose stand tile the player is on. */
  at(position: Position | undefined): Frame | undefined {
    if (!position) return undefined;
    const map = mapOf(position);
    const found = this.find(map, position);
    return found?.kind === 'painting' ? this.frames.frame(map, found.id) : undefined;
  }

  look(position: Position | undefined): boolean {
    const frame = this.at(position);
    if (!frame?.painting) return false;
    this.shown = { map: frame.map, id: frame.id };
    if (!this.render(this.shown)) return false;
    this.panel.hidden = false;
    this.hint.hidden = true;
    this.panel.focus();
    return true;
  }

  close(): void {
    if (this.panel.contains(document.activeElement)) (document.activeElement as HTMLElement).blur();
    this.panel.hidden = true;
    this.shown = undefined;
  }

  /** Each frame: closes the panel once the player steps away, and hints at the frame they're at. */
  update(position: Position | undefined): void {
    const frame = this.at(position);
    if (this.shown && (frame?.map !== this.shown.map || frame.id !== this.shown.id)) this.close();
    this.hint.hidden = this.isOpen || !frame;
    if (frame) this.hint.textContent = hintFor(frame.painting);
  }

  private render({ map, id }: { map: string; id: string }): boolean {
    const painting = this.frames.frame(map, id)?.painting;
    if (!painting) {
      this.close();
      return false;
    }
    this.title.textContent = painting.title;
    if (this.image.getAttribute('src') !== painting.image) this.image.src = painting.image;
    this.image.alt = painting.title;
    this.artist.textContent = `by ${painting.artist.name}`;
    this.statement.textContent = painting.statement;
    return true;
  }
}

const hintFor = (painting: Painting | null): string =>
  painting
    ? `Press ${KEY} to look at “${painting.title}” by ${painting.artist.name}.`
    : 'This frame is empty.';
