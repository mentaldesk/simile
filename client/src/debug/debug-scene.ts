import Phaser from 'phaser';
import { server } from '../net';
import { claimClicks } from '../ui/target';
import { worldView } from '../ui/world-view';
import { npcAt, spriteBox } from '../world/hit';
import './debug.css';
import { renderPanel } from './panel';
import { DebugWatch } from './watch';

const MARKER_COLOUR = 0xe8b04a;

export const debugWatch = new DebugWatch(server);

export class DebugScene extends Phaser.Scene {
  private panel!: HTMLElement;
  private marker!: Phaser.GameObjects.Graphics;

  constructor() {
    super({ key: 'debug', active: true });
  }

  create(): void {
    this.panel = document.body.appendChild(document.createElement('aside'));
    this.panel.className = 'debug-panel';
    this.panel.hidden = true;
    this.marker = this.add.graphics();

    // Key-down, because the chat box stops those but lets key-ups through while the player types.
    const onKeyDown = (event: KeyboardEvent) => {
      if (!(event.code === 'Backquote' || event.key === '`') || event.repeat) return;
      if (event.target instanceof HTMLInputElement || event.target instanceof HTMLTextAreaElement) {
        return;
      }
      event.preventDefault();
      debugWatch.toggle();
    };
    const onPointerDown = ({ x, y }: Phaser.Input.Pointer) => {
      const npcId = debugWatch.open ? npcAt({ x, y }, worldView()) : undefined;
      if (npcId) debugWatch.select(npcId);
    };
    window.addEventListener('keydown', onKeyDown);
    this.input.on(Phaser.Input.Events.POINTER_DOWN, onPointerDown);
    const unclaim = claimClicks(() => debugWatch.open);
    debugWatch.onChange = () => this.render();
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.removeEventListener('keydown', onKeyDown);
      unclaim();
      this.input.off(Phaser.Input.Events.POINTER_DOWN, onPointerDown);
      debugWatch.onChange = () => {};
      this.panel.remove();
    });
  }

  update(): void {
    this.marker.clear();
    const npcId = debugWatch.watching;
    const box = npcId ? spriteBox(npcId, worldView()) : undefined;
    if (box) {
      this.marker.lineStyle(2, MARKER_COLOUR).strokeRect(box.x, box.y, box.width, box.height);
    }
  }

  private render(): void {
    this.panel.hidden = !debugWatch.open;
    if (!debugWatch.open) return;
    const scroll = this.panel.scrollTop;
    this.panel.innerHTML = renderPanel(debugWatch);
    this.panel.scrollTop = scroll;
  }
}
