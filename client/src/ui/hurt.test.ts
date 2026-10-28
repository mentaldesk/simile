import { describe, expect, it } from 'vitest';
import { ServerConnection } from '../net/connection';
import { FULL_HIT, Hurts, type Hit } from './hurt';

function watch() {
  const connection = new ServerConnection();
  const hits: Hit[] = [];
  new Hurts(connection).on((hit) => hits.push(hit));
  const send = (message: object) => connection.dispatch(JSON.stringify(message));
  const health = (health: number) => send({ type: 'player_state', player: { health } });
  return { hits, send, health };
}

describe('getting hurt', () => {
  it('is a drop in health, as strong as it is big, up to a bot’s or a dog’s', () => {
    const { hits, health } = watch();
    health(1);
    health(0.97);
    health(0.92);
    health(0.82);
    health(0.6);
    expect(hits.map(({ size }) => size)).toEqual([0.03, 0.05, 0.1, 0.22].map((size) => expect.closeTo(size)));
    expect(hits.map(({ strength }) => strength)).toEqual([0.3, 0.5, 1, 1].map((strength) => expect.closeTo(strength)));
  });

  it('is not healing, an infection’s slow drain, or the first health it hears of', () => {
    const { hits, health } = watch();
    health(0.5);
    health(0.6);
    health(1);
    for (let left = 0.99; left > 0.9; left -= 0.01) health(left);
    expect(hits).toEqual([]);
  });

  it('starts again from each snapshot, so a reconnect is not a hit', () => {
    const { hits, health, send } = watch();
    health(1);
    send({ type: 'snapshot', time: '2026-01-01T12:00:00Z', map_id: 'high_street', entities: [], conversations: [] });
    health(0.5);
    expect(hits).toEqual([]);
  });

  it('is collapsing from their wounds, at full strength, but not from hunger', () => {
    const { hits, send } = watch();
    const position = { x: 1, y: 1, map: 'house_1_floor_0' };
    send({ type: 'player_collapsed', cause: 'hunger', position });
    send({ type: 'player_collapsed', cause: 'health', position });
    expect(hits).toEqual([{ size: FULL_HIT, strength: 1 }]);
  });
});
