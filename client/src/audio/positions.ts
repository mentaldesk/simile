import type { Position } from '../net';

/** Where the speakers and the listener are, in float tiles. Undefined while unknown. */
export type PositionProvider = {
  positionOf(entityId: string): Position | undefined;
  listenerPosition(): Position | undefined;
};

const nowhere: PositionProvider = {
  positionOf: () => undefined,
  listenerPosition: () => undefined,
};
let current = nowhere;

export function setPositionProvider(provider: PositionProvider): () => void {
  current = provider;
  return () => {
    if (current === provider) current = nowhere;
  };
}

export const positions: PositionProvider = {
  positionOf: (entityId) => current.positionOf(entityId),
  listenerPosition: () => current.listenerPosition(),
};
