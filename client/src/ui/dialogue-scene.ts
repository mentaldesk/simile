import Phaser from 'phaser';
import { BubbleLayer } from './bubble-layer';
import { ChatBox } from './chat-box';
import { dialogue } from './dialogue';
import './dialogue.css';
import { LogPanel } from './log-panel';
import { ChatTarget, clicked } from './target';
import { TargetMarker } from './target-marker';
import { trackedWorld, worldView } from './world-view';

export class DialogueScene extends Phaser.Scene {
  private root!: HTMLElement;
  private bubbles!: BubbleLayer;
  private marker!: TargetMarker;
  private readonly targets = new ChatTarget(worldView, dialogue);
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

    this.marker = new TargetMarker(this.root);
    this.bubbles = new BubbleLayer(this.root);
    const log = new LogPanel(this.root, dialogue.log);
    const chat = new ChatBox(this.root, dialogue, this.targets);
    const stopInvitations = dialogue.onInvitation((npcId) => chat.invite(npcId));

    const onKeyDown = (event: KeyboardEvent) => {
      const { target, key } = event;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) return;
      if (key === 'Enter') {
        // Otherwise the same Enter reaches the input once it has focus, and sends nothing.
        event.preventDefault();
        chat.open();
      } else if (key === 'Escape') {
        chat.clear();
      } else if (key === 'Tab') {
        event.preventDefault();
        chat.cycle(event.shiftKey ? -1 : 1);
      }
    };
    const onPointerDown = ({ x, y }: Phaser.Input.Pointer) => {
      const npcId = clicked({ x, y }, worldView());
      if (npcId) chat.choose(npcId);
    };
    window.addEventListener('keydown', onKeyDown);
    this.input.on(Phaser.Input.Events.POINTER_DOWN, onPointerDown);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.removeEventListener('keydown', onKeyDown);
      this.input.off(Phaser.Input.Events.POINTER_DOWN, onPointerDown);
      stopInvitations();
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
    const view = worldView();
    this.marker.render(this.targets.current(), view, (id) => dialogue.nameOf(id));
    this.bubbles.render(dialogue.bubbles.current(), view);
  }

  private fitToCanvas(): void {
    const { left, top, width } = this.game.canvas.getBoundingClientRect();
    const fit = `translate(${left}px, ${top}px) scale(${width / this.scale.width})`;
    if (fit !== this.fitted) this.root.style.transform = this.fitted = fit;
  }
}
