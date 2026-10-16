import Phaser from 'phaser';
import { server } from '../net';
import { village } from '../world/assets';
import { terminalAt, terminalsOf, type Terminal } from '../world/terminals';
import { BubbleLayer } from './bubble-layer';
import { ChatBox } from './chat-box';
import { dialogue } from './dialogue';
import './dialogue.css';
import { onGameKey } from './keys';
import { LogPanel } from './log-panel';
import { NewsPanel } from './news-panel';
import { ChatTarget, clicked } from './target';
import { TargetMarker } from './target-marker';
import { NEWS_KEY } from './tuning';
import { PLAYER_ID, trackedWorld, worldView } from './world-view';

const terminals = terminalsOf(village);

export class DialogueScene extends Phaser.Scene {
  private root!: HTMLElement;
  private bubbles!: BubbleLayer;
  private marker!: TargetMarker;
  private news!: NewsPanel;
  private newsHint!: HTMLElement;
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

    this.news = new NewsPanel(this.root, server);
    this.newsHint = this.root.appendChild(document.createElement('div'));
    this.newsHint.className = 'news-hint';
    this.newsHint.textContent = `Press ${NEWS_KEY.toUpperCase()} to read the news.`;
    const onKeyDown = onGameKey({
      chat,
      news: () => {
        const terminal = this.terminal();
        if (terminal) this.news.open(terminal.label);
      },
    });
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
      this.news.stop();
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
    const atTerminal = this.terminal() !== undefined;
    if (!atTerminal && this.news.isOpen) this.news.close();
    this.newsHint.hidden = !atTerminal || this.news.isOpen;
  }

  private terminal(): Terminal | undefined {
    return terminalAt(terminals, worldView().positionOf(PLAYER_ID));
  }

  private fitToCanvas(): void {
    const { left, top, width } = this.game.canvas.getBoundingClientRect();
    const fit = `translate(${left}px, ${top}px) scale(${width / this.scale.width})`;
    if (fit !== this.fitted) this.root.style.transform = this.fitted = fit;
  }
}
