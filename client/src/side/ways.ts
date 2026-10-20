import type { Village } from './maps';
import type { Way } from './player';

const FLOORS = ['the ground floor', 'the first floor', 'the second floor', 'the third floor'];

const floorName = (floor: number) => FLOORS[floor] ?? `floor ${floor}`;

function buildingName(village: Village, building: string | undefined): string {
  const [ground] = village.floors(building ?? '');
  const label = ground?.locations.find(({ name }) => name === building)?.props.label;
  return typeof label === 'string' ? label : (building ?? 'the building');
}

/** The hint for what E, or up at a door, takes where the player stands; with E taken, only up's. */
export function wayHint(village: Village, way: Way, eTaken = false): string | undefined {
  if (!('link' in way)) {
    if (eTaken) return undefined;
    const up = way.distance === 0 ? 'up' : 'down';
    return way.run.kind === 'ladder' ? `Press E to climb ${up} the ladder.` : `Press E to take the stairs ${up}.`;
  }
  const { link } = way;
  const [here, there] = [village.map(link.map), village.map(link.to.map)];
  if (link.kind === 'door') {
    const press = eTaken ? 'Press ↑' : 'Press E or ↑';
    if (there?.kind === 'floor') return `${press} to go into ${buildingName(village, there.building)}.`;
    const street = there?.label ?? link.to.map;
    return here?.kind === 'floor' ? `${press} to go out onto ${street}.` : `${press} to go to ${street}.`;
  }
  if (eTaken) return undefined;
  const to = there?.floor ?? 0;
  if (link.kind === 'lift') return `Press E to take the lift to ${floorName(to)}.`;
  const up = to > (here?.floor ?? 0) ? 'up' : 'down';
  return link.kind === 'ladder' ? `Press E to climb ${up} the ladder.` : `Press E to take the stairs ${up}.`;
}
