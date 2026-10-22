import type { Item, LampMessage, PlayerStateMessage } from '../net';

export const LAMP_KEY = 'L';
/** The charge below which the lamp's light draws in and the gauge warns. */
export const LOW = 0.2;

/** Whether the player stands in the dark or at a plug, as the side scene last drew them. */
export const lampHere = { dark: false, plug: false };

export const lampOf = (state: PlayerStateMessage | undefined): Item | undefined =>
  state?.player.items.find(({ kind }) => kind === 'lamp');

export const shining = (lamp: Item | undefined): boolean => !!lamp?.on && (lamp.charge ?? 0) > 0;

/** What L sends: the lamp switched the other way, unless there's none or it's flat and off. */
export function switchLamp(lamp: Item | undefined): LampMessage | undefined {
  if (!lamp || (!lamp.on && !lamp.charge)) return undefined;
  return { type: 'lamp', on: !lamp.on };
}
