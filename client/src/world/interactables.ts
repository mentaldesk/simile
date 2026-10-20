import type { Position } from '../net';
import { maps } from './assets';
import { mapOf, objectsOf, propertyOf, tileOf, type Tile, type TiledMap } from './map';

export const INTERACTABLES_LAYER = 'interactables';

export type Interactable = {
  id: string;
  kind: string;
  label: string;
  map: string;
  /** What it covers, in tiles. */
  area: Area;
  stand: Tile[];
  prompt: string;
};

export type Area = { x: number; y: number; width: number; height: number };

const lowerFirst = (text: string) => text.charAt(0).toLowerCase() + text.slice(1);

const PROMPTS: Record<string, (label: string) => string> = {
  counter: () => 'Order at the counter',
  painting: () => 'Look at the painting',
  machine: (label) => `Use the ${lowerFirst(label)}`,
};

const tiles = (stand: unknown): Tile[] =>
  typeof stand !== 'string'
    ? []
    : stand
        .split(/\s+/)
        .filter(Boolean)
        .map((pair) => {
          const [x, y] = pair.split(',').map(Number);
          return { x, y };
        });

export function interactablesOf(id: string, map: TiledMap): Interactable[] {
  return objectsOf(map, INTERACTABLES_LAYER).map((object) => {
    const label = propertyOf(object, 'label');
    const name = typeof label === 'string' ? label : object.name;
    return {
      id: object.name,
      kind: object.type,
      label: name,
      map: id,
      area: {
        x: (object.x ?? 0) / map.tilewidth,
        y: (object.y ?? 0) / map.tileheight,
        width: (object.width ?? 0) / map.tilewidth,
        height: (object.height ?? 0) / map.tileheight,
      },
      stand: tiles(propertyOf(object, 'stand')),
      prompt: PROMPTS[object.type]?.(name) ?? name,
    };
  });
}

const byMap = new Map<string, Interactable[]>();

/** The interactables on a map, once it's loaded. */
export function interactablesOn(map: string): readonly Interactable[] {
  const tiled = maps[map];
  if (!tiled) return [];
  let found = byMap.get(map);
  if (!found) byMap.set(map, (found = interactablesOf(map, tiled)));
  return found;
}

/** The interactable whose stand tile the position is on, as the server reads it. */
export function interactableAt(map: string, position: Position | undefined): Interactable | undefined {
  if (!position) return undefined;
  const { x, y } = tileOf(position);
  return interactablesOn(map).find(({ stand }) => stand.some((tile) => tile.x === x && tile.y === y));
}

type Listener = (interactable: Interactable | undefined) => void;

/** Tells listeners when the player steps onto an interactable's stand tile, and off it. */
export class InteractableWatch {
  current?: Interactable;
  private readonly listeners = new Set<Listener>();
  private readonly find: (map: string, position: Position) => Interactable | undefined;

  constructor(find: (map: string, position: Position) => Interactable | undefined = interactableAt) {
    this.find = find;
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  update(position: Position | undefined): void {
    const next = position && this.find(mapOf(position), position);
    if (next === this.current) return;
    this.current = next;
    for (const listener of this.listeners) listener(next);
  }
}

/** The world scene updates it with the player's position each frame. */
export const interactables = new InteractableWatch();
