import Phaser from 'phaser';
import { BubbleLayer } from './bubble-layer';
import { ChatBox } from './chat-box';
import { chatTarget, dialogue } from './dialogue';
import './dialogue.css';
import { LogPanel } from './log-panel';
import { trackedWorld, worldView } from './world-view';

export class DialogueScene extends Phaser.Scene {
  private root!: HTMLElement;
  private bubbles!: BubbleLayer;
  private fitted = '';

  constructor() {
    super({ key: 'dialogue', active: true });
  }

  create(): void {
    this.root = document.body.appendChild(document.createElement('div'));
    this.root.className = 'dialogue';
    this.root.style.width = `${this.scale.width}px`;
    this.root.style.height = `${this.scale.height}px`;
    trackedWorld.viewport = { width: this.scale.width, height: this.scale.height };

    this.bubbles = new BubbleLayer(this.root);
    const log = new LogPanel(this.root, dialogue.log);
    const chat = new ChatBox(this.root, dialogue, () => chatTarget(worldView()));

    const onKeyDown = (event: KeyboardEvent) => {
      const { target, key } = event;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
      if (key === 'Enter') {
        // Otherwise the same Enter reaches the input once it has focus, and sends nothing.
        event.preventDefault();
        chat.open();
      } else if (key === 'Escape') {
        chat.close();
      }
    };
    window.addEventListener('keydown', onKeyDown);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.removeEventListener('keydown', onKeyDown);
      log.stop();
      this.root.remove();
    });

    if (import.meta.env.DEV && new URLSearchParams(location.search).get('harness') === 'dialogue') {
      void import('./harness').then(({ startHarness }) => startHarness(this, this.root));
    }
    this.fitToCanvas();
  }

  update(): void {
    this.fitToCanvas();
    this.bubbles.render(dialogue.bubbles.current(), worldView());
  }

  private fitToCanvas(): void {
    const { left, top, width } = this.game.canvas.getBoundingClientRect();
    const fit = `translate(${left}px, ${top}px) scale(${width / this.scale.width})`;
    if (fit !== this.fitted) this.root.style.transform = this.fitted = fit;
  }
}
