import type { Village } from './maps';
import type { Way } from './player';

const FLOORS = ['the ground floor', 'the first floor', 'the second floor', 'the third floor'];

const floorName = (floor: number) => FLOORS[floor] ?? `floor ${floor}`;

function buildingName(village: Village, building: string | undefined): string {
  const [ground] = village.floors(building ?? '');
  const label = ground?.locations.find(({ name }) => name === building)?.props.label;
  return typeof label === 'string' ? label : (building ?? 'the building');
}

/** The hint for what E, or up at a door, takes where the player stands. */
export function wayHint(village: Village, way: Way): string {
  if (!('link' in way)) {
    const up = way.distance === 0 ? 'up' : 'down';
    return way.run.kind === 'ladder' ? `Press E to climb ${up} the ladder.` : `Press E to take the stairs ${up}.`;
  }
  const { link } = way;
  const [here, there] = [village.map(link.map), village.map(link.to.map)];
  if (link.kind === 'door') {
    if (there?.kind === 'floor') return `Press E or ↑ to go into ${buildingName(village, there.building)}.`;
    const street = there?.label ?? link.to.map;
    return here?.kind === 'floor' ? `Press E or ↑ to go out onto ${street}.` : `Press E or ↑ to go to ${street}.`;
  }
  const to = there?.floor ?? 0;
  if (link.kind === 'lift') return `Press E to take the lift to ${floorName(to)}.`;
  const up = to > (here?.floor ?? 0) ? 'up' : 'down';
  return link.kind === 'ladder' ? `Press E to climb ${up} the ladder.` : `Press E to take the stairs ${up}.`;
}
