import type { Cell, SideMap } from './maps';

const stands = (stand: unknown): Cell[] =>
  typeof stand === 'string'
    ? stand
        .split(/\s+/)
        .filter(Boolean)
        .map((pair) => {
          const [x, y] = pair.split(',').map(Number);
          return { x, y };
        })
    : [];

/** Whether a jack, a machine only the datajack works, is stood at from `cell`, as the lift is from its link. */
export function jackAt(map: SideMap, cell: Cell): boolean {
  return map.interactables.some(
    ({ type, props }) => type === 'jack' && stands(props.stand).some(({ x, y }) => x === cell.x && y === cell.y),
  );
}
