import iconManifest from '../../../content/icons/icons.json';
import type { Pile, Position } from '../net';
import type { Clue } from '../world/clues';
import { mapOf } from '../world/map';
import { eUse, reachables, type Reachable, type Reachables, type WayPrompt } from '../world/reach';
import { DEPTH } from './depths';
import { furnitureKey } from './draw';
import { feetOf, furniturePlacement, PPM, stretchWidth, xOf } from './layout';
import type { Placed, SideMap, Village } from './maps';
import type { SceneryManifest } from './scenery';

export type UsableKind = 'clue' | 'searchable' | 'jack' | 'terminal' | 'pile';

type Placing = { x: number; y: number; originX: number; originY: number; depth: number };
/** A piece of furniture the street view draws, in world px, stretched to `stretch` px wide. */
export type PieceSprite = Placing & { piece: string; stretch?: number };
/** An icon from `content/icons/`, `height` world px tall. */
export type IconSprite = Placing & { icon: string; height: number };
export type Sprite = PieceSprite | IconSprite;

/** Something E uses, drawn where the map puts it. */
export type Usable = {
  id: string;
  kind: UsableKind;
  map: string;
  /** Its building, for one on a floor, which shows only while the front is open. */
  building?: string;
  picture: Sprite;
  /** The schematic lying on a searchable that teaches a recipe, until it's searched. */
  recipe?: IconSprite;
  /** Where a painted tick marks it searched. */
  searched?: { x: number; y: number; depth: number };
};

export type UsableState = { searched: readonly string[]; piles: readonly Pile[]; clues: readonly Clue[] };

const ICONS: Record<string, { size: number[] }> = iconManifest.icons;

/** Metres tall. */
const ICON_M = { schematic: 0.34, pile: 0.4 };
/** Pinned `pinned` metres up the wall, over the player's head. */
const CLUES: Record<string, { icon: string; m: number; pinned: number }> = {
  aris_notes: { icon: 'aris_notes', m: 0.55, pinned: 2.2 },
};
/** Metres up a piece that things lie at, where that isn't near its top. */
const SURFACE_M: Record<string, number> = { workbench: 0.66 };
const TOP = 0.92;
const ABOVE = 0.1;

export const thingId = (map: string, id: string): string => `${map}/${id}`;
export const clueId = (id: string): string => `clue:${id}`;
export const pileId = ({ at }: Pile): string => `pile:${at.map}:${at.x},${at.y}`;
/** A pile keeps its id as its first item changes, and its picture with it. */
export const glowKey = ({ id, picture }: Usable): string => `${id}|${'icon' in picture ? picture.icon : picture.piece}`;

const area = ({ w, h }: Placed) => w * h;
const shared = (a: Placed, b: Placed) =>
  Math.max(0, Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x)) *
  Math.max(0, Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y));
const fit = (a: Placed, b: Placed) => shared(a, b) / (area(a) + area(b) - shared(a, b));

/** The drawn piece of furniture that best covers `thing`. */
function furnitureOver(manifest: SceneryManifest, map: SideMap, thing: Placed): Placed | undefined {
  const drawn = map.furniture.filter((piece) => manifest.furniture[piece.name] && fit(piece, thing) > 0);
  return drawn.sort((a, b) => fit(b, thing) - fit(a, thing))[0];
}

const depthOf = (map: SideMap, onWall = false) =>
  map.kind === 'street' ? DEPTH.streetFurniture : onWall ? DEPTH.frame : DEPTH.furniture;

function pieceSprite(manifest: SceneryManifest, map: SideMap, item: Placed): PieceSprite | undefined {
  const piece = furnitureKey(manifest, item, map.id);
  if (!piece) return undefined;
  const { x, y, originX, originY } = furniturePlacement(item, map);
  const stretch = manifest.furniture[item.name]?.stretch ? { stretch: stretchWidth(item) } : {};
  return { piece, ...stretch, x, y, originX, originY, depth: depthOf(map, originY < 1) };
}

const iconWidth = (icon: string, height: number) => {
  const [width, tall] = ICONS[icon]?.size ?? [1, 1];
  return (height * width) / tall;
};

export function boxOf(manifest: SceneryManifest, sprite: Sprite) {
  const size = 'piece' in sprite ? manifest.pieces[sprite.piece].size : undefined;
  const [width, height] = size
    ? [(sprite as PieceSprite).stretch ?? size[0], size[1]]
    : [iconWidth((sprite as IconSprite).icon, (sprite as IconSprite).height), (sprite as IconSprite).height];
  return { left: sprite.x - sprite.originX * width, top: sprite.y - sprite.originY * height, width, height };
}

/** In the middle of `thing`'s bottom row, on the floor or on the furniture there. */
function iconOn(manifest: SceneryManifest, map: SideMap, thing: Placed, icon: string, m: number): IconSprite {
  const x = xOf(map.offset.x + thing.x + (thing.w - 1) / 2);
  const under = furnitureOver(manifest, map, { ...thing, y: thing.y + thing.h - 1, h: 1 });
  const base = under && pieceSprite(manifest, map, under);
  const lift = under && base ? (SURFACE_M[under.name] ?? manifest.pieces[base.piece].height * TOP) * PPM : 0;
  const y = (base?.y ?? feetOf(map.offset.y + thing.y + thing.h - 1)) - lift;
  return { icon, height: m * PPM, x, y, originX: 0.5, originY: 1, depth: (base?.depth ?? depthOf(map)) + ABOVE };
}

function cluePicture(map: SideMap, clue: Clue): IconSprite | undefined {
  const look = CLUES[clue.id];
  if (!look) return undefined;
  const y = feetOf(map.offset.y + clue.y) - look.pinned * PPM;
  return { icon: look.icon, height: look.m * PPM, x: xOf(map.offset.x + clue.x), y, originX: 0.5, originY: 1, depth: DEPTH.stairs + ABOVE };
}

function tickOn(manifest: SceneryManifest, sprite: Sprite) {
  const { left, top, width, height } = boxOf(manifest, sprite);
  return { x: left + width / 2, y: top + Math.min(height * 0.45, 0.6 * PPM), depth: sprite.depth + ABOVE };
}

/** What E uses on the street shown and its floors, and what each looks like. */
export function usablesOn(village: Village, manifest: SceneryManifest, street: SideMap, state: UsableState): Usable[] {
  const maps = [street, ...street.buildings.flatMap(({ name }) => village.floors(name))];
  return maps.flatMap((map) => {
    const at = { map: map.id, ...(map.kind === 'floor' && { building: map.building }) };
    const drawn = (thing: Placed) => {
      const under = furnitureOver(manifest, map, thing);
      return under && pieceSprite(manifest, map, under);
    };
    const found: Usable[] = [];
    for (const thing of map.interactables) {
      if (thing.type !== 'searchable' && thing.type !== 'jack') continue;
      const picture = drawn(thing);
      if (!picture) continue;
      const usable: Usable = { id: thingId(map.id, thing.name), kind: thing.type, ...at, picture };
      if (state.searched.includes(thing.name)) usable.searched = tickOn(manifest, picture);
      else if (thing.type === 'searchable' && thing.props.teaches) {
        usable.recipe = iconOn(manifest, map, thing, 'schematic', ICON_M.schematic);
      }
      found.push(usable);
    }
    for (const terminal of map.locations.filter(({ type }) => type === 'terminal')) {
      const picture = drawn(terminal);
      if (picture) found.push({ id: thingId(map.id, terminal.name), kind: 'terminal', ...at, picture });
    }
    for (const clue of state.clues.filter((clue) => clue.map === map.id)) {
      const picture = cluePicture(map, clue);
      if (picture) found.push({ id: clueId(clue.id), kind: 'clue', ...at, picture });
    }
    for (const pile of state.piles.filter(({ at, items }) => at.map === map.id && items.length)) {
      const icon = ICONS[pile.items[0].id] ? pile.items[0].id : 'unknown_item';
      const picture: IconSprite = {
        icon,
        height: ICON_M.pile * PPM,
        x: xOf(map.offset.x + pile.at.x),
        y: feetOf(map.offset.y + pile.at.y),
        originX: 0.5,
        originY: 1,
        depth: depthOf(map) + ABOVE,
      };
      found.push({ id: pileId(pile), kind: 'pile', ...at, picture });
    }
    return found;
  });
}

function reachedId(reached: Reachable): string | undefined {
  switch (reached.kind) {
    case 'clue':
      return clueId(reached.clue.id);
    case 'searchable':
    case 'jack':
      return thingId(reached.interactable.map, reached.interactable.id);
    case 'terminal':
      return thingId(reached.terminal.map, reached.terminal.id);
    case 'pile':
      return pileId(reached.pile);
    default:
      return undefined;
  }
}

/** What E uses where the player stands, unless it needs the datajack they lack; with it, the lift E rides. */
export function glowing(position: Position | undefined, ways: readonly WayPrompt[], from: Reachables = reachables): string | undefined {
  if (!position) return undefined;
  const jacked = !!from.jacked?.();
  const used = eUse(position, ways, from);
  if (used) return used.kind === 'jack' && !jacked ? undefined : reachedId(used);
  const jack = from.interactableAt(mapOf(position), position);
  return jack?.kind === 'jack' && jacked && from.leadsAway?.(jack) ? thingId(jack.map, jack.id) : undefined;
}
