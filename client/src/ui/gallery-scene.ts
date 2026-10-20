import Phaser from 'phaser';
import type { Position } from '../net';
import { interactableAt } from '../world/interactables';
import { galleryFrames } from '../world/paintings';
import { usedByE } from '../world/reach';
import './dialogue.css';
import { GalleryPanel } from './gallery-panel';
import { pressedNewsKey, unfocused } from './keys';
import { fitOverlay } from './overlay';
import { PLAYER_ID, worldView } from './world-view';

/** The gallery panel, over the game in an overlay of its own like the dialogue UI's. */
export class GalleryScene extends Phaser.Scene {
  private root!: HTMLElement;
  private panel!: GalleryPanel;
  private fitted = '';

  constructor() {
    super({ key: 'gallery-panel', active: true });
  }

  create(): void {
    this.root = document.body.appendChild(document.createElement('div'));
    this.root.className = 'dialogue';
    this.panel = new GalleryPanel(this.root, galleryFrames, interactableAt);
    const onKeyDown = (event: KeyboardEvent) => {
      if (!unfocused(event) || !pressedNewsKey(event)) return;
      const player = this.player();
      if (usedByE(player)?.kind === 'painting' && this.panel.look(player)) event.preventDefault();
    };
    window.addEventListener('keydown', onKeyDown);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.removeEventListener('keydown', onKeyDown);
      this.panel.stop();
      this.root.remove();
    });
  }

  update(): void {
    const canvas = this.game.canvas.getBoundingClientRect();
    const { scale, width, height } = fitOverlay(canvas, this.scale.gameSize);
    const transform = `translate(${canvas.left}px, ${canvas.top}px) scale(${scale})`;
    const fit = `${transform} ${width}x${height}`;
    if (fit !== this.fitted) {
      this.fitted = fit;
      Object.assign(this.root.style, { width: `${width}px`, height: `${height}px`, transform });
    }
    this.panel.update(this.player());
  }

  private player(): Position | undefined {
    return worldView().positionOf(PLAYER_ID);
  }
}
