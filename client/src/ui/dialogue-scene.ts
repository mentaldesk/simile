import Phaser from 'phaser';
import { playerState, server, type Position } from '../net';
import { maps } from '../world/assets';
import type { Interactable } from '../world/interactables';
import { deadJack, jacked } from '../world/jacks';
import { muralWalls } from '../world/murals';
import { foundIn } from '../world/searchables';
import { usedByE, wayPrompts, type Reachable } from '../world/reach';
import { BubbleLayer } from './bubble-layer';
import { callCue } from './call-cue';
import { CharacterPanel } from './character-panel';
import { ChatBox } from './chat-box';
import { ClinicPanel, type Keeper } from './clinic-panel';
import { CounterPrompt, servingAt } from './counter';
import { dialogue } from './dialogue';
import './dialogue.css';
import { HelpPanel } from './help';
import { HungerHint, toEat } from './hunger';
import { JournalPanel, lookAtClue } from './journal-panel';
import { eUse, onGameKey } from './keys';
import { LampGauge } from './lamp-gauge';
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
  private lamp!: LampGauge;
  private journal!: JournalPanel;
  private help!: HelpPanel;
  private character!: CharacterPanel;
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
    const stopCollapses = server.on('player_collapsed', ({ cause }) => hunger.collapsed(cause));
    this.lamp = new LampGauge(this.root);
    const journal = (this.journal = new JournalPanel(this.root));
    const help = (this.help = new HelpPanel(this.root));
    const character = (this.character = new CharacterPanel(this.root));
    const onKeyDown = onGameKey({ chat, use: () => this.pressE(), eat: () => this.eat(), help, journal, character });
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
      journal.stop();
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
    const prompted = used?.kind === 'counter' || used?.kind === 'jack' || used?.kind === 'searchable';
    const counter = prompted ? used.interactable : undefined;
    this.counter.update(counter, !this.chat.isOpen);
    this.clinic.update(used?.kind === 'clinic' ? used.buyer : undefined, playerState.latest?.player, this.keeper(), playerState.latest?.recipes);
    const state = playerState.latest && this.clinic.isOpen ? { ...playerState.latest, buyer: null } : playerState.latest;
    this.hunger.update(state, used?.kind === 'pile' ? used.pile : undefined);
    this.lamp.update(playerState.latest);
    this.character.update(playerState.latest);
    const panelOpen = this.news.isOpen || this.murals.isOpen || this.clinic.isOpen || this.character.isOpen;
    this.journal.update(used?.kind === 'clue' ? used.clue : undefined, !panelOpen);
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
    this.character.close();
    if (used?.kind === 'counter') this.order(used.interactable);
    else if (used?.kind === 'terminal') {
      this.murals.close();
      this.news.open(used.terminal.label);
    } else if (used?.kind === 'mural') this.murals.look(this.player());
    else if (used?.kind === 'pile') server.send({ type: 'pick_up' });
    else if (used?.kind === 'buyer') server.send({ type: 'sell', item: null });
    else if (used?.kind === 'clue') lookAtClue((message) => server.send(message), this.journal, this.help);
    else if (used?.kind === 'jack') this.useJack(used.interactable);
    else if (used?.kind === 'searchable') {
      server.send({ type: 'pick_up' });
      this.counter.flash(foundIn(used.interactable));
    }
    else if (used?.kind === 'clinic' && playerState.latest) {
      this.murals.close();
      this.news.close();
      this.clinic.open(used.buyer, playerState.latest.player, this.keeper(), playerState.latest.recipes);
    }
  }

  /** With the datajack, E at a jack finds the clue in it, as at a clue; without, it's dead. */
  private useJack(jack: Interactable): void {
    if (!jacked(playerState.latest?.player.body)) this.counter.flash(deadJack(jack));
    else lookAtClue((message) => server.send(message), this.journal, this.help);
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
