import { afterEach, describe, expect, it } from 'vitest';
import { playerState, server } from '../net';
import { DOOR_FADE_OUT_SECONDS, SEND_INTERVAL_SECONDS } from '../world/tuning';
import { village } from './content';
import { SidePlayer, type Controls, type MapPosition } from './player';
import { MoveReport } from './report';

const DT = 1 / 60;
const BED = { x: 5, y: 2, map: 'maker_space_floor_2' };
const idle: Controls = { x: 0, y: 0, use: false, run: false };

describe('reporting moves', () => {
  afterEach(() => {
    playerState.latest = undefined;
  });

  it('sends a move at most every SEND_INTERVAL_SECONDS, and none standing still', () => {
    const moves = new MoveReport();
    expect(moves.next({ x: 1, y: 15, map: 'high_street' }, 0)).toEqual({ x: 1, y: 15, map: 'high_street' });
    expect(moves.next({ x: 1.5, y: 15, map: 'high_street' }, SEND_INTERVAL_SECONDS / 2)).toBeUndefined();
    expect(moves.next({ x: 1.5, y: 15, map: 'high_street' }, SEND_INTERVAL_SECONDS)).toEqual({ x: 1.5, y: 15, map: 'high_street' });
    expect(moves.next({ x: 1.5, y: 15, map: 'high_street' }, 1)).toBeUndefined();
  });

  it('wakes a player who collapsed while moving still resting in their bed', () => {
    const moves = new MoveReport();
    const player = new SidePlayer(village, { x: 10, y: 15, map: 'high_street' });
    let on: MapPosition = { ...player.mapPosition };
    const resting = () => on.map === BED.map && Math.round(on.x) === BED.x && Math.round(on.y) === BED.y;
    const tell = () =>
      server.dispatch(JSON.stringify({ type: 'player_state', player: { money: 0, items: [] }, ...(resting() && { bed: BED, resting: true }) }));
    let now = 0;
    const report = () => {
      const move = moves.next(player.mapPosition, now);
      if (!move) return;
      on = move;
      tell();
    };
    const frame = (controls: Controls) => {
      player.update(controls, DT);
      now += DT;
      report();
    };
    for (let i = 0; i < 20; i++) frame({ ...idle, x: 1 });
    expect(on.x).toBeLessThan(player.position.x);

    on = { ...BED };
    moves.collapsed();
    tell();
    for (let t = 0; t < DOOR_FADE_OUT_SECONDS + SEND_INTERVAL_SECONDS; t += DT) {
      now += DT;
      report();
    }
    player.place(BED);
    moves.woke();
    for (let i = 0; i < 30; i++) frame(idle);
    expect(on).toEqual(BED);
    expect(resting()).toBe(true);
    expect(player.drawn.bed).toBe(1);
  });

  it('sends moves again once woken, even if they walk off at once', () => {
    const moves = new MoveReport();
    const player = new SidePlayer(village, { x: 10, y: 15, map: 'high_street' });
    const sent: MapPosition[] = [];
    let now = 0;
    moves.collapsed();
    player.place(BED);
    moves.woke();
    for (let t = 0; t < 2; t += DT) {
      player.update({ ...idle, x: 1 }, DT);
      now += DT;
      const move = moves.next(player.mapPosition, now);
      if (move) sent.push(move);
    }
    expect(sent.length).toBeGreaterThan(5);
    expect(sent.at(-1)!.x).toBeGreaterThan(BED.x);
  });
});
