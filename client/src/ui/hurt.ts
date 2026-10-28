import { server } from '../net';
import type { ServerConnection } from '../net/connection';

/** Health lost at once below which it's an infection's slow drain, not a hit: the server sends health every 0.01. */
export const LEAST_HIT = 0.015;
/** Health lost at once that gives a hit full strength: a bot's or a dog's. */
export const FULL_HIT = 0.1;

/** A hit's `size` is the health it took, `strength` that from 0 to 1: a bat's 0.3, a rat's 0.5, a bot's 1. */
export type Hit = { size: number; strength: number };
type Listener = (hit: Hit) => void;

export const strengthOf = (size: number): number => Math.min(size / FULL_HIT, 1);

export class Hurts {
  private readonly listeners = new Set<Listener>();
  private health?: number;

  constructor(connection: Pick<ServerConnection, 'on'> = server) {
    connection.on('snapshot', () => (this.health = undefined));
    connection.on('player_state', ({ player }) => this.feel(player.health ?? 1));
    connection.on('player_collapsed', ({ cause }) => cause === 'health' && this.hit(FULL_HIT));
  }

  on(listener: Listener): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }

  private feel(health: number): void {
    const before = this.health;
    this.health = health;
    if (before !== undefined && before - health >= LEAST_HIT) this.hit(before - health);
  }

  private hit(size: number): void {
    const hit = { size, strength: strengthOf(size) };
    for (const listener of this.listeners) listener(hit);
  }
}

export const hurts = new Hurts();
