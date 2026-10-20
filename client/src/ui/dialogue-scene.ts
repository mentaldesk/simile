import Phaser from 'phaser';
import { server, type Position } from '../net';
import { maps, village } from '../world/assets';
import { interactables } from '../world/interactables';
import { muralWalls } from '../world/iso/murals';
import { terminalAt, terminalsOf, type Terminal } from '../world/terminals';
import { BubbleLayer } from './bubble-layer';
import { ChatBox } from './chat-box';
import { counterOf, CounterPrompt, servingAt } from './counter';
import { dialogue } from './dialogue';
import './dialogue.css';
import { onGameKey } from './keys';
import { LogPanel } from './log-panel';
import { MuralPanel } from './mural-panel';
import { NewsPanel } from './news-panel';
import { fitOverlay, inOverlay } from './overlay';
import { setMaps } from './side-view';
import { ChatTarget, clicked } from './target';
import { TargetMarker } from './target-marker';
import { NEWS_KEY } from './tuning';
import { PLAYER_ID, trackedWorld, worldView } from './world-view';

const terminals = terminalsOf(village);
setMaps(maps);

export class DialogueScene extends Phaser.Scene {
  private root!: HTMLElement;
  private bubbles!: BubbleLayer;
  private marker!: TargetMarker;
  private news!: NewsPanel;
  private newsHint!: HTMLElement;
  private murals!: MuralPanel;
  private counter!: CounterPrompt;
  private chat!: ChatBox;
  private readonly targets = new ChatTarget(worldView, dialogue);
  private fitted = '';
  private fromGame = 1;

  constructor() {
    super({ key: 'dialogue', active: true });
  }

  create(): void {
    this.root = document.body.appendChild(document.createElement('div'));
    this.root.className = 'dialogue';

    this.marker = new TargetMarker(this.root);
    this.bubbles = new BubbleLayer(this.root);
    const log = new LogPanel(this.root, dialogue.log);
    const chat = (this.chat = new ChatBox(this.root, dialogue, this.targets));
    const stopInvitations = dialogue.onInvitation((npcId) => chat.invite(npcId));

    this.news = new NewsPanel(this.root, server);
    this.newsHint = this.root.appendChild(document.createElement('div'));
    this.newsHint.className = 'news-hint';
    this.newsHint.textContent = `Press ${NEWS_KEY.toUpperCase()} to read the news.`;
    this.murals = new MuralPanel(this.root, muralWalls);
    this.counter = new CounterPrompt(this.root);
    const onKeyDown = onGameKey({
      chat,
      news: () => {
        if (this.order()) return;
        const terminal = this.terminal();
        if (!terminal) {
          this.murals.look(this.player());
          return;
        }
        this.murals.close();
        this.news.open(terminal.label);
      },
    });
    const onPointerDown = ({ x, y }: Phaser.Input.Pointer) => {
      const npcId = clicked({ x, y }, worldView());
      if (npcId) chat.choose(npcId);
      else if (this.murals.click({ x, y }, this.player())) this.news.close();
    };
    window.addEventListener('keydown', onKeyDown);
    this.input.on(Phaser.Input.Events.POINTER_DOWN, onPointerDown);
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => {
      window.removeEventListener('keydown', onKeyDown);
      this.input.off(Phaser.Input.Events.POINTER_DOWN, onPointerDown);
      stopInvitations();
      this.news.stop();
      this.murals.stop();
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
    const view = inOverlay(worldView(), this.fromGame);
    this.marker.render(this.targets.current(), view, (id) => dialogue.nameOf(id));
    this.bubbles.render(dialogue.bubbles.current(), view);
    const atTerminal = this.terminal() !== undefined;
    if (!atTerminal && this.news.isOpen) this.news.close();
    this.newsHint.hidden = !atTerminal || this.news.isOpen || this.murals.isOpen;
    this.murals.update(this.player(), !atTerminal && !this.news.isOpen);
    this.counter.update(counterOf(interactables.current), !this.chat.isOpen);
  }

  /** At a counter, E opens the chat to whoever is serving behind it. */
  private order(): boolean {
    const counter = counterOf(interactables.current);
    if (!counter) return false;
    const serving = servingAt(counter, worldView()) ?? dialogue.partner();
    if (!serving) {
      this.counter.flash("Nobody's behind the counter.");
      return true;
    }
    this.chat.choose(serving);
    this.chat.open();
    return true;
  }

  private player(): Position | undefined {
    return worldView().positionOf(PLAYER_ID);
  }

  private terminal(): Terminal | undefined {
    return terminalAt(terminals, this.player());
  }

  private fitToCanvas(): void {
    const canvas = this.game.canvas.getBoundingClientRect();
    const { scale, width, height, fromGame } = fitOverlay(canvas, this.scale.gameSize);
    this.fromGame = fromGame;
    const transform = `translate(${canvas.left}px, ${canvas.top}px) scale(${scale})`;
    const fit = `${transform} ${width}x${height}`;
    if (fit === this.fitted) return;
    this.fitted = fit;
    Object.assign(this.root.style, { width: `${width}px`, height: `${height}px`, transform });
    trackedWorld.viewport = { width: this.scale.width, height: this.scale.height };
    trackedWorld.scale = 1 / fromGame;
  }
}
