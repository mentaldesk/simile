import type { TiledMap, TiledProperty } from '../world/map';
import './place-label.css';

type Maps = Readonly<Record<string, TiledMap | undefined>>;

/** How long a new place's name stands out before it settles. */
export const NEW_PLACE_SECONDS = 2.5;

const property = (properties: TiledProperty[] | undefined, name: string): unknown =>
  properties?.find((property) => property.name === name)?.value;

/** A street's `label`, or for a floor its building's, from the front on its street (content/street/README.md). */
export function placeName(maps: Maps, mapId: string): string | undefined {
  const map = maps[mapId];
  if (!map) return undefined;
  if (property(map.properties, 'kind') !== 'floor') return property(map.properties, 'label') as string | undefined;
  const building = property(map.properties, 'building');
  const street = maps[String(property(map.properties, 'street'))];
  const front = street?.layers.find(({ name }) => name === 'buildings')?.objects?.find(({ name }) => name === building);
  return property(front?.properties, 'label') as string | undefined;
}

/** The name of the place the player is in, standing out for a moment whenever it changes. */
export class PlaceLabel {
  private readonly root: HTMLElement;
  private shown?: string;
  private settleAt = 0;
  private readonly maps: Maps;

  constructor(parent: HTMLElement, maps: Maps) {
    this.maps = maps;
    this.root = parent.appendChild(document.createElement('div'));
    this.root.className = 'place-label';
    this.root.hidden = true;
  }

  /** `now` in seconds. */
  update(mapId: string | undefined, now: number): void {
    const name = mapId === undefined ? undefined : placeName(this.maps, mapId);
    if (name !== this.shown) {
      this.shown = name;
      this.root.hidden = !name;
      this.root.textContent = name ?? '';
      this.settleAt = now + NEW_PLACE_SECONDS;
    }
    this.root.classList.toggle('place-label-new', !!name && now < this.settleAt);
  }
}
