import Phaser from 'phaser';
import { setPositionProvider } from '../audio';
import { addAtlas } from '../dolls/paper-doll';
import { server, type Position } from '../net';
import { PLAYER_ID, setWorldView, type ScreenSprite, type WorldView } from '../ui/world-view';
import { dollFor } from '../world/assets';
import { interactables } from '../world/interactables';
import { muralWalls, setMuralView } from '../world/murals';
import { galleryFrames } from '../world/paintings';
import { setWayHint, usedByE } from '../world/reach';
import { MoveThrottle } from '../world/throttle';
import { DOOR_FADE_IN_SECONDS, DOOR_FADE_OUT_SECONDS, MAX_FRAME_SECONDS } from '../world/tuning';
import { follow, sideZoom, viewCentre } from './camera';
import { sideClock } from './clock';
import { DEPTH } from './depths';
import { DOLL_M, feetOf, PPM, xOf } from './layout';
import { emptyLight, lightAt } from './light';
import type { Link, Village } from './maps';
import type { Drawn } from './motion';
import type { Crossing } from './runs';
import { SidePlayer, type Controls, type MapPosition } from './player';
import { sideResidents } from './residents';
import { SideDoll } from './side-doll';
import { StreetView, type Content } from './street-view';
import { SideTextures } from './textures';
import { wayHint } from './ways';

export const SIDE_SCENE = 'side-world';

/** When the snapshot's player isn't on a side-view map. */
const DEFAULT_START: MapPosition = { x: 51, y: 15, map: 'high_street' };
const KEYS = 'UP,DOWN,LEFT,RIGHT,W,A,S,D';
/** Half a sim minute. */
const LIGHT_STEP_HOURS = 1 / 120;
const DOLL_WIDTH_M = 0.7;
const CONTACT_M = 0.9;
const BUBBLE_GAP_M = 0.15;
/** Room for the target's name, so a speech bubble sits over it. */
const NAME_M = 0.45;

type Keys = Record<'UP' | 'DOWN' | 'LEFT' | 'RIGHT' | 'W' | 'A' | 'S' | 'D', Phaser.Input.Keyboard.Key>;
type Figure = { id: string; doll: SideDoll; contact: Phaser.GameObjects.Image; x: number; feet: number; shown: boolean };

const harness = import.meta.env.DEV && new URLSearchParams(globalThis.location?.search ?? '').get('harness') === 'side';

/** The village from the side: README.md. */
export class SideScene extends Phaser.Scene {
  private content?: Content;
  private pictures!: SideTextures;
  private street?: StreetView;
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
  private readonly controls: Controls = { x: 0, y: 0, use: false };
  private passing = false;
  private worksChanged = true;
  private snap = true;
  /** A tap shorter than a frame still counts. */
  private used = false;

  constructor() {
    super(SIDE_SCENE);
  }

  create(): void {
    this.scene.sendToBack();
    this.pictures = new SideTextures(this);
    const camera = this.cameras.main;
    camera.setBackgroundColor('#9fc3d8').fadeOut(0);
    const keyboard = this.input.keyboard!;
    this.keys = keyboard.addKeys(KEYS, false) as Keys;
    keyboard.on('keydown-E', (event: KeyboardEvent) => (this.used ||= !event.repeat));
    const cleanups = [
      setWorldView(this.worldView()),
      setPositionProvider({
        positionOf: (id) => this.positionOf(id),
        listenerPosition: () => this.positionOf(PLAYER_ID),
      }),
      server.on('snapshot', () => this.throttle.forget()),
      setMuralView({
        wallAt: ({ x, y }) => {
          const point = this.cameras.main.getWorldPoint(x, y);
          return this.street?.muralAt(point.x, point.y);
        },
      }),
      setWayHint(() => this.hint()),
      muralWalls.onChange(() => (this.worksChanged = true)),
      galleryFrames.onChange(() => (this.worksChanged = true)),
      () => interactables.update(undefined),
      () => this.street?.destroy(),
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
    const start = this.startPosition(content.village);
    this.player = new SidePlayer(content.village, start);
    await this.showStreet(content.village.map(start.map)!.street);
    this.cameras.main.fadeIn(DOOR_FADE_IN_SECONDS * 1000);
  }

  /** For the dev harness. */
  teleport(to: MapPosition): void {
    this.takeDoorTo(to);
  }

  update(time: number, delta: number): void {
    const { content, player, street } = this;
    if (!content || !player || !street) return;
    const dt = Math.min(delta / 1000, MAX_FRAME_SECONDS);
    if (!this.passing) {
      const door = player.update(this.read(player), dt);
      if (door) this.takeDoor(door);
    }
    interactables.update(player.mapPosition);
    sideResidents.update(dt);
    const hour = sideClock.hour();
    const lightChanged = !(Math.abs(hour - this.lightHour) < LIGHT_STEP_HOURS);
    if (lightChanged) {
      lightAt(hour, content.scenery, this.light);
      this.lightHour = hour;
    }
    const open = content.village.map(player.drawnMap);
    this.frame(dt, street);
    street.update(this.view, this.light, lightChanged, open?.kind === 'floor' ? open.building : undefined, dt);
    if (this.worksChanged) {
      this.worksChanged = false;
      const load = (url: string) => this.pictures.load(`work:${url}`, url);
      street.setMurals(muralWalls.walls, load);
      street.setPaintings(galleryFrames.frames, load);
    }
    this.drawFigures(content.village, street);
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

  private startPosition(village: Village): MapPosition {
    const start = sideResidents.start;
    return start && village.map(start.map) ? start : DEFAULT_START;
  }

  /** E uses what's in reach before any door, stairs, ladder or lift. */
  private read(player: SidePlayer): Controls {
    const { controls, keys } = this;
    controls.x = Number(keys.RIGHT.isDown || keys.D.isDown) - Number(keys.LEFT.isDown || keys.A.isDown);
    controls.y = Number(keys.DOWN.isDown || keys.S.isDown) - Number(keys.UP.isDown || keys.W.isDown);
    controls.use = this.used && !usedByE(player.mapPosition);
    this.used = false;
    return controls;
  }

  private hint(): string | undefined {
    const { content, player } = this;
    const way = !this.passing && player?.way();
    return way ? wayHint(content!.village, way) : undefined;
  }

  private frame(dt: number, street: StreetView): void {
    const camera = this.cameras.main;
    const zoom = sideZoom(camera);
    if (zoom !== camera.zoom) camera.setZoom(zoom);
    const { at } = this.player!;
    const { size, feet } = this;
    size.width = camera.width / zoom;
    size.height = camera.height / zoom;
    feet.x = xOf(at.x);
    feet.y = feetOf(at.y);
    viewCentre(feet, street.feet, street.width, size, this.target);
    if (this.snap) {
      this.centre.x = this.target.x;
      this.centre.y = this.target.y;
      this.snap = false;
    } else follow(this.centre, this.target, dt, this.centre);
    camera.centerOn(this.centre.x, this.centre.y);
    this.view.setTo(this.centre.x - size.width / 2, this.centre.y - size.height / 2, size.width, size.height);
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
      this.drawFigure(PLAYER_ID, player.drawnMap, player.at, player.drawn, village, street);
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
  ): void {
    const figure = this.figure(id);
    if (!figure) return;
    const map = village.map(mapId);
    const inside = map?.kind === 'floor';
    const shown = map?.street === street.map.id && (!inside || street.isOpen(map.building));
    figure.shown = shown;
    figure.doll.setVisible(shown);
    figure.contact.setVisible(shown && drawn.on !== 'ladder' && drawn.pose !== 'riding');
    if (!shown) return;
    figure.x = xOf(at.x);
    figure.feet = feetOf(at.y);
    const depth = (inside ? DEPTH.insideDoll : DEPTH.doll) + figure.feet * 1e-7;
    const alpha = inside ? 1 : street.ghost(figure.x);
    figure.doll.setPosition(figure.x, figure.feet).setDepth(depth).setAlpha(alpha);
    figure.doll.show(drawn, street.tints.colours[inside ? 'inside' : 'ground']);
    figure.contact.setPosition(figure.x, figure.feet).setAlpha(alpha);
    figure.contact.setDepth(inside ? DEPTH.insideContact : DEPTH.contact);
  }

  private figure(id: string): Figure | undefined {
    const known = this.figures.get(id);
    if (known || this.loadingDolls.has(id)) return known;
    this.loadingDolls.add(id);
    const doll = dollFor(id);
    const flat = `doll-${id}-flat`;
    void addAtlas(this, flat, doll.flat, doll).then(() => {
      if (!this.sys.isActive()) return;
      const sideDoll = new SideDoll(this, doll, flat);
      this.add.existing(sideDoll);
      const contact = this.add.image(0, 0, this.pictures.contact()).setOrigin(0.5, 0.5);
      contact.setDisplaySize(CONTACT_M * PPM, CONTACT_M * PPM * 0.25);
      this.figures.set(id, { id, doll: sideDoll, contact, x: 0, feet: 0, shown: false });
      if (!doll.painted) return;
      const painted = `doll-${id}-painted`;
      addAtlas(this, painted, doll.painted, doll).then(
        () => sideDoll.paint(painted),
        (error: unknown) => console.warn(error),
      );
    });
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
