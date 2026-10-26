import Phaser from 'phaser';
import { setPositionProvider } from '../audio';
import { addFigureAtlas } from '../dolls/sprite-figure';
import { playerState, server, type Position } from '../net';
import { PLAYER_ID, setWorldView, type ScreenSprite, type WorldView } from '../ui/world-view';
import { dollFor } from '../world/assets';
import { interactables } from '../world/interactables';
import { muralWalls, setMuralView } from '../world/murals';
import { galleryFrames } from '../world/paintings';
import { reachables, setWayPrompts, type WayPrompt } from '../world/reach';
import { MoveThrottle } from '../world/throttle';
import { DOOR_FADE_IN_SECONDS, DOOR_FADE_OUT_SECONDS, MAX_FRAME_SECONDS } from '../world/tuning';
import { follow, sideZoom, viewCentre } from './camera';
import { sideClock } from './clock';
import { CreatureView } from './creatures/view';
import { DarkView } from './dark-view';
import { atPlug, glowAround, hasDark, isLit, sightOf } from './darkness';
import { kick, KICK_KEY } from './kick';
import { lampHere, lampOf, switchLamp } from './lamp';
import { DEPTH } from './depths';
import { eachOnce, readControls, RunToggle, type Held } from './input';
import { DOLL_M, feetOf, PPM, xOf } from './layout';
import { emptyLight, lightAt, lightBelow, UNDERGROUND } from './light';
import { cellOf, type Link, type Village } from './maps';
import type { Drawn } from './motion';
import type { Crossing } from './runs';
import { SidePlayer, type Controls, type MapPosition } from './player';
import { jumpOf } from './jump';
import { fitted } from '../dolls/bionics';
import { drawSockets } from './plugs';
import { sideResidents } from './residents';
import { PileGlints } from './piles';
import { hiddenInFront, seatHeight } from './poses';
import { SideDoll } from './side-doll';
import { StreetView, type Content } from './street-view';
import { SideTextures } from './textures';
import { prompts } from './ways';

export const SIDE_SCENE = 'side-world';

/** When the snapshot's player isn't on a side-view map. */
const DEFAULT_START: MapPosition = { x: 51, y: 15, map: 'high_street' };
const KEYS = 'UP,DOWN,LEFT,RIGHT,W,A,S,D,SPACE';
/** Above the end of a way, where its prompt sits: under a room's ceiling, or over a street's signposts. */
const PROMPT_M = { floor: 2.75, street: 3.35 };
/** Half a sim minute. */
const LIGHT_STEP_HOURS = 1 / 120;
const DOLL_WIDTH_M = 0.7;
const CONTACT_M = 0.9;
const BUBBLE_GAP_M = 0.15;
/** Room for the target's name, so a speech bubble sits over it. */
const NAME_M = 0.45;
/** Metres up at which a jumping figure's shadow on the ground has faded away. */
const SHADOW_FADE_M = 6;

const contactAlpha = (up: number) => Math.max(0, 1 - up / SHADOW_FADE_M);

type Keys = Record<'UP' | 'DOWN' | 'LEFT' | 'RIGHT' | 'W' | 'A' | 'S' | 'D' | 'SPACE', Phaser.Input.Keyboard.Key>;
type Figure = { id: string; doll: SideDoll; contact: Phaser.GameObjects.Image; x: number; feet: number; shown: boolean };

const harness = import.meta.env.DEV && new URLSearchParams(globalThis.location?.search ?? '').get('harness') === 'side';

/** The village from the side: README.md. */
export class SideScene extends Phaser.Scene {
  private content?: Content;
  private pictures!: SideTextures;
  private glints!: PileGlints;
  private creatures!: CreatureView;
  private street?: StreetView;
  private dark?: DarkView;
  private sockets: Phaser.GameObjects.Graphics[] = [];
  private player?: SidePlayer;
  private keys!: Keys;
  private readonly figures = new Map<string, Figure>();
  private readonly loadingDolls = new Set<string>();
  private readonly light = emptyLight();
  private lightHour = NaN;
  private readonly throttle = new MoveThrottle();
  private readonly view = new Phaser.Geom.Rectangle();
  private readonly centre = { x: 0, y: 0 };
  private readonly target = { x: 0, y: 0 };
  private readonly feet = { x: 0, y: 0 };
  private readonly size = { width: 0, height: 0 };
  private readonly sent = { x: NaN, y: NaN, map: '' };
  private readonly held: Held = { up: false, down: false, left: false, right: false, run: false };
  private readonly controls: Controls = { x: 0, y: 0, use: false, eTaken: false, run: false };
  private readonly running = new RunToggle();
  private jumped = false;
  private passing = false;
  /** Where they wake once the street is shown and any door they are going through is done. */
  private waking?: MapPosition;
  private worksChanged = true;
  private snap = true;
  /** A tap shorter than a frame still counts. */
  private used = false;
  private readonly tapped = { up: false, down: false };

  constructor() {
    super(SIDE_SCENE);
  }

  create(): void {
    this.scene.sendToBack();
    this.pictures = new SideTextures(this);
    this.glints = new PileGlints(this);
    this.creatures = new CreatureView(this);
    const camera = this.cameras.main;
    camera.setBackgroundColor('#9fc3d8').fadeOut(0);
    const keyboard = this.input.keyboard!;
    this.keys = keyboard.addKeys(KEYS, false) as Keys;
    keyboard.on('keydown-E', (event: KeyboardEvent) => (this.used ||= !event.repeat));
    keyboard.on('keydown-SPACE', (event: KeyboardEvent) => (this.jumped ||= !event.repeat));
    keyboard.on('keydown-L', eachOnce((event: KeyboardEvent) => !event.repeat && this.switchLamp()));
    keyboard.on(`keydown-${KICK_KEY}`, eachOnce((event: KeyboardEvent) => !event.repeat && this.kick()));
    keyboard.on('keydown', eachOnce((event: KeyboardEvent) => this.running.keyDown(event.key, event.repeat)));
    keyboard.on('keyup', eachOnce((event: KeyboardEvent) => this.running.keyUp(event.key)));
    for (const key of ['UP', 'W']) keyboard.on(`keydown-${key}`, () => (this.tapped.up = true));
    for (const key of ['DOWN', 'S']) keyboard.on(`keydown-${key}`, () => (this.tapped.down = true));
    const cleanups = [
      setWorldView(this.worldView()),
      setPositionProvider({
        positionOf: (id) => this.positionOf(id),
        listenerPosition: () => this.positionOf(PLAYER_ID),
      }),
      server.on('snapshot', () => {
        this.throttle.forget();
        this.sent.map = '';
      }),
      server.on('player_collapsed', ({ position: { x, y, map } }) => this.wake({ x, y, map: map ?? '' })),
      setMuralView({
        wallAt: ({ x, y }) => {
          const point = this.cameras.main.getWorldPoint(x, y);
          return this.street?.muralAt(point.x, point.y);
        },
      }),
      setWayPrompts((eTaken) => this.prompts(eTaken)),
      muralWalls.onChange(() => (this.worksChanged = true)),
      galleryFrames.onChange(() => (this.worksChanged = true)),
      () => interactables.update(undefined),
      () => this.street?.destroy(),
      () => this.dark?.destroy(),
      () => this.glints.destroy(),
      () => this.creatures.destroy(),
      () => this.pictures.destroy(),
    ];
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => cleanups.forEach((cleanup) => cleanup()));
    void this.start();
  }

  private async start(): Promise<void> {
    const content = await import('./content');
    this.content = content;
    sideResidents.village = content.village;
    if (harness) {
      const { startHarness } = await import('./harness');
      startHarness(this, content.village);
    }
    const start = this.waking ?? this.startPosition(content.village);
    this.waking = undefined;
    this.player = new SidePlayer(content.village, start);
    await this.showStreet(content.village.map(start.map)!.street);
    this.cameras.main.fadeIn(DOOR_FADE_IN_SECONDS * 1000);
    this.wakeIfWaiting();
  }

  /** For the dev harness. */
  teleport(to: MapPosition): void {
    this.takeDoorTo(to);
  }

  /** For the dev harness. */
  get playing(): SidePlayer | undefined {
    return this.player;
  }

  /** For the dev harness. */
  get runningOn(): boolean {
    return this.running.on;
  }

  update(time: number, delta: number): void {
    const { content, player, street } = this;
    if (!content || !player || !street) return;
    const dt = Math.min(delta / 1000, MAX_FRAME_SECONDS);
    const body = playerState.latest?.player.body;
    const jump = jumpOf(body);
    player.rise = jump.rise;
    player.runSpeed = jump.run;
    player.datajack = fitted(body).includes('datajack');
    if (!this.passing) {
      const door = player.update(this.read(player), dt);
      if (door) this.takeDoor(door);
    }
    interactables.update(player.mapPosition);
    sideResidents.update(dt);
    const below = street.map.underground;
    const hour = below ? UNDERGROUND.hour : sideClock.hour();
    const lightChanged = !(Math.abs(hour - this.lightHour) < LIGHT_STEP_HOURS);
    if (lightChanged) {
      if (below) lightBelow(content.scenery, this.light);
      else lightAt(hour, content.scenery, this.light);
      this.lightHour = hour;
    }
    const open = content.village.map(player.drawnMap);
    this.frame(dt, street);
    street.update(this.view, this.light, lightChanged, open?.kind === 'floor' ? open.building : undefined, dt);
    this.dark?.update(glowAround(player.at, lampOf(playerState.latest)));
    const cell = cellOf(player.at);
    lampHere.dark = !!this.dark && !isLit(street.map, cell.x, cell.y);
    lampHere.plug = atPlug(player.mapPosition);
    if (this.worksChanged) {
      this.worksChanged = false;
      const load = (url: string) => this.pictures.load(`work:${url}`, url);
      street.setMurals(muralWalls.walls, load);
      street.setPaintings(galleryFrames.frames, load);
    }
    this.drawFigures(content.village, street);
    this.creatures.update(content.village, street.map.id, street.tints.colours.ground, dt);
    this.glints.update(content.village, street.map.id, reachables.piles(), time / 1000);
    this.report(player.mapPosition, time / 1000);
  }

  private report(position: MapPosition, now: number): void {
    const { sent } = this;
    if (position.x === sent.x && position.y === sent.y && position.map === sent.map) return;
    const throttled = this.throttle.next(position, now);
    if (!throttled) return;
    server.send({ type: 'player_move', position: throttled });
    sent.x = position.x;
    sent.y = position.y;
    sent.map = position.map;
  }

  private switchLamp(): void {
    const message = switchLamp(lampOf(playerState.latest));
    if (message) server.send(message);
  }

  private kick(): void {
    const facing = this.passing ? undefined : this.player?.kick();
    if (facing) server.send(kick(facing));
  }

  private startPosition(village: Village): MapPosition {
    const start = sideResidents.start;
    return start && village.map(start.map) ? start : DEFAULT_START;
  }

  private read(player: SidePlayer): Controls {
    const { held, keys, tapped } = this;
    held.up = keys.UP.isDown || keys.W.isDown || tapped.up;
    held.down = keys.DOWN.isDown || keys.S.isDown || tapped.down;
    held.left = keys.LEFT.isDown || keys.A.isDown;
    held.right = keys.RIGHT.isDown || keys.D.isDown;
    held.run = this.running.on;
    held.jump = this.jumped;
    held.hold = keys.SPACE.isDown;
    readControls(held, this.used, player.mapPosition, this.controls);
    this.used = this.jumped = tapped.up = tapped.down = false;
    return this.controls;
  }

  /** Each in game-canvas px, over the end of its way. */
  private prompts(eTaken: boolean): WayPrompt[] {
    const { content, player } = this;
    const map = player && content?.village.map(player.map);
    if (!map || this.passing) return [];
    const zoom = this.cameras.main.zoom;
    return prompts(content!.village, map, player!.ways(), eTaken).map(({ at, keys, action }) => ({
      keys,
      action,
      x: (xOf(map.offset.x + at.x) - this.view.x) * zoom,
      y: (feetOf(map.offset.y + at.y) - PROMPT_M[map.kind] * PPM - this.view.y) * zoom,
    }));
  }

  private frame(dt: number, street: StreetView): void {
    const camera = this.cameras.main;
    const zoom = sideZoom(camera);
    if (zoom !== camera.zoom) camera.setZoom(zoom);
    const { steady } = this.player!;
    const { size, feet } = this;
    size.width = camera.width / zoom;
    size.height = camera.height / zoom;
    feet.x = xOf(steady.x);
    feet.y = feetOf(steady.y);
    viewCentre(feet, street.feet, street.width, size, this.target);
    if (this.snap) {
      this.centre.x = this.target.x;
      this.centre.y = this.target.y;
      this.snap = false;
    } else follow(this.centre, this.target, dt, this.centre);
    camera.centerOn(this.centre.x, this.centre.y);
    this.view.setTo(this.centre.x - size.width / 2, this.centre.y - size.height / 2, size.width, size.height);
  }

  /** The server moved them home after they collapsed. */
  private wake(at: MapPosition): void {
    if (this.passing || !this.street) this.waking = at;
    else this.takeDoorTo(at);
  }

  private wakeIfWaiting(): void {
    const waking = this.waking;
    this.waking = undefined;
    if (waking) this.takeDoorTo(waking);
  }

  private takeDoor(door: Link): void {
    this.takeDoorTo({ x: door.to.x, y: door.to.y, map: door.to.map });
  }

  /** A front door just opens the dollhouse; another street fades out and in. */
  private takeDoorTo(to: MapPosition): void {
    const { content, player, street } = this;
    const map = content?.village.map(to.map);
    if (!content || !player || !street || !map || this.passing) return;
    if (map.street === street.map.id) {
      player.place(to);
      return;
    }
    this.passing = true;
    const camera = this.cameras.main;
    camera.fadeOut(DOOR_FADE_OUT_SECONDS * 1000);
    camera.once(Phaser.Cameras.Scene2D.Events.FADE_OUT_COMPLETE, async () => {
      try {
        await this.showStreet(map.street);
        player.place(to);
      } finally {
        this.passing = false;
        camera.fadeIn(DOOR_FADE_IN_SECONDS * 1000);
        this.wakeIfWaiting();
      }
    });
  }

  private async showStreet(id: string): Promise<void> {
    const content = this.content!;
    const map = content.village.map(id)!;
    const keys = StreetView.pieces(content, map);
    await Promise.all(keys.map((key) => this.pictures.load(key, content.pieceUrl(key))));
    const old = this.street;
    if (old) {
      old.destroy();
      const kept = new Set(keys);
      for (const key of StreetView.pieces(content, old.map)) if (!kept.has(key)) this.pictures.unload(key);
    }
    this.street = new StreetView(this, this.pictures, content, map);
    this.dark?.destroy();
    this.dark = hasDark(map) ? new DarkView(this, sightOf(map)) : undefined;
    for (const socket of this.sockets) socket.destroy();
    this.sockets = drawSockets(this, content.village, map);
    this.lightHour = NaN;
    this.worksChanged = true;
    this.snap = true;
  }

  private drawFigures(village: Village, street: StreetView): void {
    for (const resident of sideResidents.all.values()) {
      this.drawFigure(resident.id, resident.drawnMap, resident.at, resident.drawn, village, street);
      const under = resident.under;
      if (under?.crossing.kind === 'lift') this.ride(under.crossing, resident.at, street, resident.drawnMap);
    }
    const { player } = this;
    if (player) {
      this.drawFigure(PLAYER_ID, player.drawnMap, player.at, player.drawn, village, street, player.ground);
      const crossing = player.riding;
      if (crossing) this.ride(crossing, player.at, street, player.drawnMap);
    }
    for (const figure of this.figures.values()) {
      if (figure.id === PLAYER_ID || sideResidents.all.has(figure.id)) continue;
      figure.shown = false;
      figure.doll.setVisible(false);
      figure.contact.setVisible(false);
    }
    street.endRides();
  }

  private ride(
    crossing: Crossing,
    at: { x: number; y: number },
    street: StreetView,
    mapId: string,
  ): void {
    const building = this.content!.village.map(mapId)?.building;
    const { points } = crossing.path;
    if (!building || !street.isOpen(building)) return;
    street.ride(building, xOf(points[1].x), feetOf(at.y), feetOf(points[0].y), feetOf(points.at(-1)!.y));
  }

  private drawFigure(
    id: string,
    mapId: string,
    at: { x: number; y: number },
    drawn: Drawn,
    village: Village,
    street: StreetView,
    ground = at.y,
  ): void {
    const figure = this.figure(id);
    if (!figure) return;
    const map = village.map(mapId);
    const inside = map?.kind === 'floor';
    const x = xOf(at.x);
    const shown =
      map?.street === street.map.id &&
      (!inside || street.isOpen(map.building)) &&
      !hiddenInFront(inside, id === PLAYER_ID, street.ghost(x));
    figure.shown = shown;
    figure.doll.setVisible(shown);
    figure.contact.setVisible(shown && drawn.on !== 'ladder' && drawn.pose !== 'riding');
    if (!shown) return;
    figure.x = x;
    figure.feet = feetOf(at.y);
    const depth = (inside ? DEPTH.insideDoll : DEPTH.doll) + figure.feet * 1e-7;
    figure.doll.setPosition(figure.x, figure.feet).setDepth(depth);
    const seat = map ? seatHeight(map, at.x - map.offset.x, at.y - map.offset.y) : 0;
    figure.doll.show(drawn, street.tints.colours[inside ? 'inside' : 'ground'], seat);
    const below = feetOf(ground);
    figure.contact.setPosition(figure.x, below).setAlpha(contactAlpha((below - figure.feet) / PPM));
    figure.contact.setDepth(inside ? DEPTH.insideContact : DEPTH.contact);
  }

  private figure(id: string): Figure | undefined {
    const known = this.figures.get(id);
    if (known || this.loadingDolls.has(id)) return known;
    this.loadingDolls.add(id);
    const figure = dollFor(id);
    const key = `figure-${figure.id ?? id}`;
    void addFigureAtlas(this, key, figure).then(
      () => {
        if (!this.sys.isActive()) return;
        const sideDoll = new SideDoll(this, figure, key);
        this.add.existing(sideDoll);
        const contact = this.add.image(0, 0, this.pictures.contact()).setOrigin(0.5, 0.5);
        contact.setDisplaySize(CONTACT_M * PPM, CONTACT_M * PPM * 0.25);
        this.figures.set(id, { id, doll: sideDoll, contact, x: 0, feet: 0, shown: false });
      },
      (error: unknown) => console.warn(error),
    );
    return undefined;
  }

  private positionOf(id: string): Position | undefined {
    if (id === PLAYER_ID) return this.player && { ...this.player.mapPosition };
    const resident = sideResidents.all.get(id);
    if (!resident) return undefined;
    const { x, y } = resident.walker.position;
    return { x, y, map: resident.map };
  }

  private worldView(): WorldView {
    const canvasBox = (id: string) => {
      const figure = this.figures.get(id);
      if (!figure?.shown) return undefined;
      const zoom = this.cameras.main.zoom;
      const half = (DOLL_WIDTH_M * PPM) / 2;
      const top = figure.feet - (DOLL_M + BUBBLE_GAP_M) * PPM;
      return {
        x: (figure.x - half - this.view.x) * zoom,
        y: (top - this.view.y) * zoom,
        width: 2 * half * zoom,
        height: (figure.feet - top) * zoom,
      };
    };
    return {
      positionOf: (id) => this.positionOf(id),
      npcIds: () => {
        const map = this.player?.map;
        return [...sideResidents.all.values()].filter((resident) => resident.map === map).map(({ id }) => id);
      },
      bubbleAnchor: (id) => {
        const box = canvasBox(id);
        return box && { x: box.x + box.width / 2, y: box.y - NAME_M * PPM * this.cameras.main.zoom };
      },
      spriteOf: (id): ScreenSprite | undefined => {
        const box = canvasBox(id);
        return box && { box, depth: box.y + box.height };
      },
    };
  }
}
