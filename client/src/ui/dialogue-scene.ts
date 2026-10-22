import Phaser from 'phaser';
import { playerState, server, type Position } from '../net';
import { maps } from '../world/assets';
import type { Interactable } from '../world/interactables';
import { muralWalls } from '../world/murals';
import { usedByE, wayPrompts, type Reachable } from '../world/reach';
import { BubbleLayer } from './bubble-layer';
import { callCue } from './call-cue';
import { ChatBox } from './chat-box';
import { ClinicPanel, type Keeper } from './clinic-panel';
import { CounterPrompt, servingAt } from './counter';
import { dialogue } from './dialogue';
import './dialogue.css';
import { HelpPanel } from './help';
import { HungerHint, toEat } from './hunger';
import { eUse, onGameKey } from './keys';
import { LogPanel } from './log-panel';
import { MuralPanel } from './mural-panel';
import { NewsPanel } from './news-panel';
import { fitOverlay, inOverlay } from './overlay';
import { setMaps } from './side-view';
import { ChatTarget, clicked } from './target';
import { TargetMarker } from './target-marker';
import { WayPromptLayer } from './way-prompts';
import { NEWS_KEY } from './tuning';
import { PLAYER_ID, trackedWorld, worldView } from './world-view';

setMaps(maps);

export class DialogueScene extends Phaser.Scene {
  private root!: HTMLElement;
  private bubbles!: BubbleLayer;
  private marker!: TargetMarker;
  private news!: NewsPanel;
  private newsHint!: HTMLElement;
  private ways!: WayPromptLayer;
  private murals!: MuralPanel;
  private clinic!: ClinicPanel;
  private counter!: CounterPrompt;
  private hunger!: HungerHint;
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
    const stopInvitations = dialogue.onInvitation((npcId) => {
      chat.invite(npcId);
      callCue.show(npcId, dialogue.nameOf(npcId));
    });

    this.news = new NewsPanel(this.root, server);
    this.newsHint = this.root.appendChild(document.createElement('div'));
    this.newsHint.className = 'news-hint';
    this.newsHint.textContent = `Press ${NEWS_KEY.toUpperCase()} to read the news.`;
    this.ways = new WayPromptLayer(this.root);
    this.murals = new MuralPanel(this.root, muralWalls);
    this.clinic = new ClinicPanel(this.root, (message) => server.send(message), (npcId) => {
      chat.choose(npcId);
      chat.open();
    });
    this.counter = new CounterPrompt(this.root);
    const hunger = (this.hunger = new HungerHint(this.root));
    const stopCollapses = server.on('player_collapsed', () => hunger.collapsed());
    const help = new HelpPanel(this.root);
    const onKeyDown = onGameKey({ chat, use: () => this.pressE(), eat: () => this.eat(), help });
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
      stopCollapses();
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
    this.bubbles.render(dialogue.bubbles.current(), view);
    callCue.update(dialogue.partner());
    const player = this.player();
    const used = usedByE(player);
    const atTerminal = used?.kind === 'terminal';
    if (!atTerminal && this.news.isOpen) this.news.close();
    this.newsHint.hidden = !atTerminal || this.news.isOpen || this.murals.isOpen;
    this.murals.update(player, used?.kind === 'mural' && !this.news.isOpen);
    this.counter.update(used?.kind === 'counter' ? used.interactable : undefined, !this.chat.isOpen);
    this.clinic.update(used?.kind === 'clinic' ? used.buyer : undefined, playerState.latest?.player, this.keeper());
    const state = playerState.latest && this.clinic.isOpen ? { ...playerState.latest, buyer: null } : playerState.latest;
    this.hunger.update(state, used?.kind === 'pile' ? used.pile : undefined);
    const panelOpen = this.news.isOpen || this.murals.isOpen || this.clinic.isOpen;
    const ways = panelOpen ? [] : wayPrompts(used !== undefined);
    this.ways.render(ways, this.fromGame);
    const target = this.targets.current();
    const talks = !panelOpen && !this.chat.isOpen && eUse(used, ways, target)?.kind === 'talk';
    this.marker.render(target, view, (id) => dialogue.nameOf(id), talks);
  }

  private pressE(): void {
    const used = usedByE(this.player());
    const e = eUse(used, wayPrompts(used !== undefined), this.targets.current());
    if (e?.kind === 'reach') this.use(e.reachable);
    else if (e?.kind === 'talk') this.chat.open();
  }

  /** E uses the nearest thing in reach; the gallery scene looks at paintings. */
  private use(used: Reachable | undefined): void {
    if (used?.kind === 'counter') this.order(used.interactable);
    else if (used?.kind === 'terminal') {
      this.murals.close();
      this.news.open(used.terminal.label);
    } else if (used?.kind === 'mural') this.murals.look(this.player());
    else if (used?.kind === 'pile') server.send({ type: 'pick_up' });
    else if (used?.kind === 'buyer') server.send({ type: 'sell', item: null });
    else if (used?.kind === 'clinic' && playerState.latest) {
      this.murals.close();
      this.news.close();
      this.clinic.open(used.buyer, playerState.latest.player, this.keeper());
    }
  }

  /** Whoever the player could talk to at the clinic: the doctor, once they're ringed. */
  private keeper(): Keeper | undefined {
    const id = this.targets.current();
    return id === undefined ? undefined : { id, name: dialogue.nameOf(id) };
  }

  /** F has the meal on offer here if they can pay, else eats something they carry. */
  private eat(): void {
    const eat = toEat(playerState.latest);
    if (eat) server.send({ type: 'eat', item: eat.kind === 'item' ? eat.item.id : null });
  }

  /** At a counter, E opens the chat to whoever is serving behind it. */
  private order(counter: Interactable): void {
    const serving = servingAt(counter, worldView()) ?? dialogue.partner();
    if (!serving) {
      this.counter.flash("Nobody's behind the counter.");
      return;
    }
    this.chat.choose(serving);
    this.chat.open();
  }

  private player(): Position | undefined {
    return worldView().positionOf(PLAYER_ID);
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
