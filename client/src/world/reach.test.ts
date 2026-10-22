import { afterEach, describe, expect, it } from 'vitest';
import { server, type Pile, type Wall } from '../net';
import { muralWalls, setMuralView } from './murals';
import { inReach, pileInReach, reachables, setWayPrompts, usedByE, wayPrompts, type Reachables } from './reach';
import type { Terminal } from './terminals';

const mural = (id: string, map: string, x: number, width: number): Wall => ({
  id,
  map,
  x,
  y: 15,
  width,
  face: 'south',
  bottom: 1,
  top: 2,
  mural: {
    work_id: `${id}-work`,
    title: id,
    artist: { id: 'kofi', name: 'Kofi Mensah' },
    statement: 'About it.',
    image: `/api/works/${id}.png`,
  },
});
/** content/street/banyan_row.tmj's wall on house 10, along cells 19 to 21. */
const HOUSE_10 = mural('banyan_row', 'banyan_row', 19, 3);
const at = (map: string, x: number, y = 15) => ({ x, y, map });

afterEach(() => server.dispatch(JSON.stringify({ type: 'murals', walls: [] })));

describe('usedByE', () => {
  it('uses the terminal, counter or painting frame the player is at', () => {
    expect(usedByE(at('high_street', 60))).toMatchObject({ kind: 'terminal', terminal: { id: 'terminal_1' } });
    expect(usedByE(at('banyan_row', 60, 18))).toMatchObject({ kind: 'terminal', terminal: { id: 'terminal_3' } });
    expect(usedByE(at('coffee_shop_floor_0', 6, 2))).toMatchObject({
      kind: 'counter',
      interactable: { id: 'coffee_shop_counter' },
    });
    expect(usedByE(at('gallery_floor_1', 14, 2))).toMatchObject({
      kind: 'painting',
      interactable: { id: 'painting_8' },
    });
  });

  it('uses nothing at a machine, at a plain door or nowhere', () => {
    expect(usedByE(at('maker_space_floor_0', 8, 2))).toBeUndefined();
    expect(usedByE(at('high_street', 43))).toBeUndefined();
    expect(usedByE(at('gallery_floor_1', 15, 2))).toBeUndefined();
    expect(usedByE(undefined)).toBeUndefined();
  });

  it('looks at the mural by house 10’s door, rather than going in, once murals are drawn', () => {
    server.dispatch(JSON.stringify({ type: 'murals', walls: [HOUSE_10] }));
    expect(usedByE(at('banyan_row', 17))).toBeUndefined();

    const unset = setMuralView({ wallAt: () => undefined });
    expect(usedByE(at('banyan_row', 17))).toMatchObject({ kind: 'mural', tiles: 1.5, wall: HOUSE_10 });
    expect(usedByE(at('banyan_row', 24))).toMatchObject({ kind: 'mural', wall: HOUSE_10 });
    expect(usedByE(at('banyan_row', 10))).toBeUndefined();
    expect(muralWalls.walls).toEqual([HOUSE_10]);
    unset();
  });
});

describe('inReach', () => {
  const terminal: Terminal = { id: 'terminal_9', label: 'Terminal', map: 'high_street', x: 30, y: 13, width: 1, height: 3 };
  const withWall = (x: number): Reachables => ({
    ...reachables,
    terminals: [terminal],
    walls: () => [mural('wall', 'high_street', x, 2)],
  });

  it('lists everything in reach, nearest first', () => {
    const kinds = (x: number, wall: number) =>
      inReach(at('high_street', x), withWall(wall)).map(({ kind, tiles }) => [kind, tiles]);
    expect(kinds(29, 26)).toEqual([
      ['terminal', 0.5],
      ['mural', 1.5],
    ]);
    expect(kinds(31, 31)).toEqual([
      ['mural', 0],
      ['terminal', 0.5],
    ]);
    expect(kinds(28, 26)).toEqual([['mural', 0.5]]);
  });
});

describe('a pile the player left', () => {
  const lamp = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 0.2, on: true } as const;
  const pile = (map: string, x: number, y = 15): Pile => ({ at: { map, x, y }, items: [lamp] });
  const left = [pile('kapok_walk', 12), pile('kapok_walk', 20), pile('rooftops', 12, 8)];
  const withPiles: Reachables = { ...reachables, piles: () => left };

  it('is in reach within a tile on its map, nearest first', () => {
    const near = pileInReach(at('kapok_walk', 12.6), left);
    expect(near?.pile).toBe(left[0]);
    expect(near?.tiles).toBeCloseTo(0.6);
    expect(pileInReach(at('kapok_walk', 19.5, 14.5), left)?.pile).toBe(left[1]);
    expect(pileInReach(at('kapok_walk', 13.1), left)).toBeUndefined();
    expect(pileInReach(at('high_street', 12), left)).toBeUndefined();
    expect(pileInReach(at('rooftops', 12, 7.2), left)?.pile).toBe(left[2]);
  });

  it('is what E picks up', () => {
    expect(inReach(at('kapok_walk', 11.5), withPiles)).toEqual([{ kind: 'pile', tiles: 0.5, pile: left[0] }]);
  });

  it('comes from the last player_state', () => {
    expect(reachables.piles()).toEqual([]);
    const body = { legs: 'present', vertebra: 'present', left_eye: 'present', right_eye: 'present', left_kidney: 'present', right_kidney: 'present' };
    const player = { money: 0, items: [], carry_limit: 10, body, hunger: 0.75, left };
    server.dispatch(JSON.stringify({ type: 'player_state', player }));

    expect(reachables.piles()).toEqual(left);
    expect(usedByE(at('kapok_walk', 20))).toMatchObject({ kind: 'pile', pile: left[1] });
    server.dispatch(JSON.stringify({ type: 'player_state', player: { ...player, left: undefined } }));
    expect(reachables.piles()).toEqual([]);
  });
});

describe('salvage, secrets and buyers', () => {
  const wire = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null } as const;
  const body = { legs: 'present', vertebra: 'present', left_eye: 'present', right_eye: 'present', left_kidney: 'present', right_kidney: 'present' };
  const theirs: Pile = { at: { map: 'metro', x: 30, y: 15 }, items: [wire] };
  const lying: Pile[] = [
    { at: { map: 'metro', x: 38, y: 12 }, items: [wire] },
    { at: { map: 'metro', x: 8, y: 7 }, items: [], money: 25 },
  ];
  const trader = { place: 'scrap_stall', name: "The scrap trader's stall", prices: { copper_wire: 6 } };
  const state = (extra: object) =>
    server.dispatch(
      JSON.stringify({
        type: 'player_state',
        player: { money: 0, items: [wire], carry_limit: 10, body, hunger: 0, left: [theirs] },
        ...extra,
      }),
    );

  afterEach(() => state({}));

  it('picks up what lies about as well as what they left', () => {
    state({ piles: lying });

    expect(reachables.piles()).toEqual([theirs, ...lying]);
    expect(usedByE(at('metro', 8.4, 7))).toMatchObject({ kind: 'pile', pile: lying[1] });
  });

  it('sells to the buyer where they stand while they carry something it buys', () => {
    state({ buyer: trader });
    expect(usedByE(at('metro', 26))).toEqual({ kind: 'buyer', tiles: 0, buyer: trader });

    state({ buyer: { ...trader, prices: {} } });
    expect(usedByE(at('metro', 26))).toBeUndefined();
  });

  it('opens the clinic while the doctor buys a part of them or fits something, and else sells', () => {
    const legs = { bionic: 'hydraulic_legs', name: 'Hydraulic legs', price: 80, parts: ['legs'] };
    const clinic = { place: 'clinic', name: 'The Clinic', prices: {}, parts: { left_kidney: 100 }, fittings: [legs] };
    state({ buyer: clinic });
    expect(usedByE(at('clinic_floor_0', 4, 2))).toEqual({ kind: 'clinic', tiles: 0, buyer: clinic });

    const fitted = { ...clinic, parts: undefined };
    state({ buyer: fitted });
    expect(usedByE(at('clinic_floor_0', 4, 2))).toMatchObject({ kind: 'clinic' });

    const salvage = { place: 'clinic', name: 'The Clinic', prices: { copper_wire: 6 } };
    state({ buyer: salvage });
    expect(usedByE(at('clinic_floor_0', 4, 2))).toEqual({ kind: 'buyer', tiles: 0, buyer: salvage });
  });
});

describe('wayPrompts', () => {
  const lift = { keys: ['E'], action: 'lift to the first floor', x: 10, y: 20 };

  it('are the world scene’s, while it says some', () => {
    expect(wayPrompts()).toEqual([]);
    const unset = setWayPrompts(() => [lift]);
    expect(wayPrompts()).toEqual([lift]);
    unset();
    expect(wayPrompts()).toEqual([]);
  });

  it('tell the world scene when E is used for something in reach', () => {
    const door = (eTaken: boolean) => ({ keys: eTaken ? ['↑'] : ['E', '↑'], action: 'go in', x: 0, y: 0 });
    const unset = setWayPrompts((eTaken) => [door(eTaken)]);
    expect(wayPrompts()[0].keys).toEqual(['E', '↑']);
    expect(wayPrompts(true)[0].keys).toEqual(['↑']);
    unset();
  });
});
