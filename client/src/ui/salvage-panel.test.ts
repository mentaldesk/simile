// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { playerState, type Bionic, type Corpse, type Item, type Pile, type Player, type PlayerStateMessage, type Position, type TakeMessage } from '../net';
import type { Reachable } from '../world/reach';
import cases from './salvage-panel.cases.json';
import { holderOf, itemRows, REFUSED_MS, SalvagePanel, takeOf, thingsOf, type Thing } from './salvage-panel';

vi.mock('./icons', () => ({ iconUrl: (id: string) => (id === 'copper_wire' ? '/icons/copper_wire.webp' : undefined) }));
vi.mock('../world/interactables', () => ({ interactableAt: () => undefined }));

const AT = { map: 'metro', x: 65, y: 15 };
const HERE: Position = { ...AT };
const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 1, on: false };
const HEAVY: Item = { id: 'scrap_steel', kind: 'salvage', name: 'Scrap steel', weight: 9.5, charge: null, on: null };
const part = (id: Bionic, name: string, weight: number): Item => ({ id, kind: 'bionic', name, weight, bionic: id, charge: null, on: null });
const JACK = part('datajack', 'Datajack', 0.5);
const LEGS = part('bionic_legs_3', 'Bionic legs, grade 3', 8);
const plastic = (amount: number): Item => ({ id: 'plastic', kind: 'material', name: 'Plastic', weight: 0.5, amount, material: 'plastic', charge: null, on: null });
const body = (held: Partial<Corpse> = {}, id = 'corpse_1'): Corpse => ({ id, owner: 'player', at: AT, money: 0, items: [], bionics: [], ...held });
const player = (more: Partial<Player> = {}): Player => ({ money: 0, items: [LAMP], carry_limit: 10, hunger: 0, ...more }) as unknown as Player;
const state = (playing: Player, bionics: Item[] = [JACK, LEGS]) => ({ player: playing, bionics }) as unknown as PlayerStateMessage;
const atBody = (corpse: Corpse): Extract<Reachable, { kind: 'pile' }> => ({ kind: 'pile', tiles: 0, pile: corpse, salvage: { corpse, others: 0, takes: true } });
const atPile = (pile: Pile): Extract<Reachable, { kind: 'pile' }> => ({ kind: 'pile', tiles: 0, pile });

describe('thingsOf', () => {
  it('lists the money, then a row per item, then a row per bionic, each against the room', () => {
    const rows = thingsOf(body({ money: 12, items: [WIRE, HEAVY, plastic(30)], bionics: ['datajack', 'bionic_legs_3'] }), 9, [JACK, LEGS]);

    expect(rows.map((row) => [row.kind, row.id, row.kind === 'money' ? row.money : row.moves])).toEqual([
      ['money', 'credits', 12],
      ['item', 'copper_wire', 1],
      ['item', 'scrap_steel', 0],
      ['item', 'plastic', 18],
      ['bionic', 'datajack', 1],
      ['bionic', 'bionic_legs_3', 1],
    ]);
  });

  it('counts two of a bionic on one row', () => {
    const eye = part('infrared_eye', 'Infrared eye', 0.5);
    const [row] = thingsOf(body({ bionics: ['infrared_eye', 'infrared_eye'] }), 9, [eye]);

    expect(row).toMatchObject({ kind: 'bionic', count: 2, load: 1, moves: 1 });
  });

  it('has a row for each item unlike the others, so two pistols are two rows, and counts what is just alike', () => {
    const pistol = (rounds: number, condition: number): Item => ({ id: 'plastic_pistol', kind: 'weapon', name: 'Plastic pistol', weight: 0.5, material: 'plastic', rounds, capacity: 6, condition, charge: null, on: null });
    const rows = itemRows([pistol(0, 0.1), WIRE, pistol(6, 1), WIRE], 9);

    expect(rows.map(({ id, index, count }) => [id, index, count])).toEqual([
      ['plastic_pistol', 0, 1],
      ['copper_wire', 1, 2],
      ['plastic_pistol', 2, 1],
    ]);
    expect(takeOf({ corpse: 'corpse_1' }, rows[2]!)).toMatchObject({ item: 'plastic_pistol', index: 2 });
  });

  it('keeps an item and a bionic of one id apart', () => {
    const rows = thingsOf(body({ items: [JACK], bionics: ['datajack'] }), 9, [JACK]);

    expect(rows.map(({ kind }) => kind)).toEqual(['item', 'bionic']);
  });

  it('has a pile as money and items', () => {
    const pile: Pile = { at: AT, items: [WIRE], money: 3 };

    expect(thingsOf(pile, 9, []).map(({ kind }) => kind)).toEqual(['money', 'item']);
  });
});

describe('takeOf', () => {
  const things = thingsOf(body({ money: 1, items: [WIRE, HEAVY], bionics: ['datajack'] }), 2, [JACK]);

  it('names the corpse and the thing, and nothing that will not fit', () => {
    const on = { corpse: 'corpse_1' };
    expect(takeOf(on, things[0]!)).toEqual({ type: 'take', corpse: 'corpse_1', pile: null, item: null, index: null, bionic: null });
    expect(takeOf(on, things[1]!)).toEqual({ type: 'take', corpse: 'corpse_1', pile: null, item: 'copper_wire', index: 0, bionic: null });
    expect(takeOf(on, things[2]!)).toBeUndefined();
    expect(things[2]).toMatchObject({ kind: 'item', index: 1 });
    expect(takeOf(on, things[3]!)).toEqual({ type: 'take', corpse: 'corpse_1', pile: null, item: null, index: null, bionic: 'datajack' });
  });

  it('names a pile by its tile', () => {
    expect(takeOf({ pile: AT }, things[1]!)).toEqual({ type: 'take', corpse: null, pile: AT, item: 'copper_wire', index: 0, bionic: null });
  });
});

describe('the screen and the server', () => {
  const movesOf = (thing: Thing) => (thing.kind === 'money' ? thing.money : thing.moves);

  it.each(cases.map((one, index) => [index, one] as const))('agree on case %i', (_, { player: playing, bionics, moves }) => {
    const carried = playing as unknown as Player;
    const room = carried.carry_limit - carried.items.reduce((load, { weight, amount = 1 }) => load + weight * amount, 0);
    const things = thingsOf(carried.corpses![0]!, room, bionics as Item[]);

    expect(things.map(({ kind, id }) => [kind, id])).toEqual(expect.arrayContaining(moves.map(({ kind, id }) => [kind, id])));
    for (const { kind, id, moved, ...at } of moves) {
      const thing = things.find((one) => one.kind === kind && one.id === id && (one.kind !== 'item' || one.index === (at as { index?: number }).index))!;
      expect(movesOf(thing)).toBeCloseTo(moved, 6);
      expect(takeOf({ corpse: 'corpse_1' }, thing) !== undefined).toBe(moved > 0);
    }
  });
});

describe('holderOf', () => {
  it('finds a corpse by its id and the oldest pile on a tile', () => {
    const [older, newer] = [body({ money: 1 }), body({ money: 2 }, 'corpse_2')];
    const piles: Pile[] = [{ at: { ...AT, x: 1 }, items: [WIRE] }, { at: AT, items: [WIRE] }, { at: AT, items: [LAMP] }];
    const playing = player({ corpses: [older, newer], left: piles });

    expect(holderOf({ corpse: 'corpse_2' }, playing)).toBe(newer);
    expect(holderOf({ corpse: 'corpse_3' }, playing)).toBeUndefined();
    expect(holderOf({ pile: AT }, playing)).toBe(piles[1]);
    expect(holderOf({ pile: { ...AT, x: 9 } }, playing)).toBeUndefined();
  });
});

describe('SalvagePanel', () => {
  let parent: HTMLElement;
  let sent: TakeMessage[];
  let panel: SalvagePanel;

  const element = () => parent.querySelector<HTMLElement>('.salvage-panel')!;
  const side = (index: number) => parent.querySelectorAll<HTMLElement>('.clinic-side')[index]!;
  const lines = (index: number) => [...side(index).querySelectorAll('li')].map((line) => line.textContent);
  const selected = () => parent.querySelector('.clinic-selected')?.textContent;
  const status = () => parent.querySelector('footer p')?.textContent;
  const press = (key: string, repeat = false) => {
    const event = new KeyboardEvent('keydown', { key, repeat, bubbles: true, cancelable: true });
    element().dispatchEvent(event);
    return event;
  };
  const opened = (playing: Player, used = atBody(playing.corpses![0]!)) => {
    playerState.latest = state(playing);
    expect(panel.open(used)).toBe(true);
  };
  const after = (playing: Player, at: Position | undefined = HERE) => {
    playerState.latest = state(playing);
    panel.update(at);
  };

  beforeEach(() => {
    parent = document.body.appendChild(document.createElement('div'));
    sent = [];
    panel = new SalvagePanel(parent, (message) => sent.push(message));
  });

  afterEach(() => {
    parent.remove();
    delete playerState.latest;
  });

  it('is no section.clinic and has no hint of its own, so the scene keeps its queries', () => {
    expect(parent.querySelector('section.clinic')).toBeNull();
    expect(parent.querySelector('.counter-hint')).toBeNull();
  });

  it('opens hidden until E, on what they carry and what the body holds, with icons and weights', () => {
    expect(panel.isOpen).toBe(false);

    opened(player({ money: 4, corpses: [body({ money: 12, items: [WIRE], bionics: ['datajack'] })] }));

    expect(panel.isOpen).toBe(true);
    expect(document.activeElement).toBe(element());
    expect(parent.querySelector('header')?.textContent).toBe('Your body');
    expect(side(0).querySelector('h3')?.textContent).toBe('You carry 1 of 10 kg');
    expect(lines(0)).toEqual(['Money4', 'Lamp1 kg']);
    expect(side(1).querySelector('h3')?.textContent).toBe('On your body');
    expect(lines(1)).toEqual(['Money12', 'Copper wire1.5 kg', 'Datajack0.5 kg']);
    expect(side(1).querySelectorAll('li')[1]!.querySelector('img')?.getAttribute('src')).toBe('/icons/copper_wire.webp');
    expect(side(1).querySelectorAll('.clinic-blank')).toHaveLength(2);
  });

  it('takes the chosen thing with Enter, and shows it move across', () => {
    const corpse = body({ money: 12, items: [WIRE], bionics: ['datajack'] });
    opened(player({ corpses: [corpse] }));
    expect(status()).toBe('Enter to take it.');

    press('Enter');
    expect(sent).toEqual([{ type: 'take', corpse: 'corpse_1', pile: null, item: null, index: null, bionic: null }]);
    after(player({ money: 12, corpses: [{ ...corpse, money: 0 }] }));
    expect(lines(0)).toEqual(['Money12', 'Lamp1 kg']);
    expect(lines(1)).toEqual(['Copper wire1.5 kg', 'Datajack0.5 kg']);
    expect(selected()).toBe('Copper wire1.5 kg');

    press('ArrowDown');
    expect(selected()).toBe('Datajack0.5 kg');
    press('Enter');
    expect(sent.at(-1)).toEqual({ type: 'take', corpse: 'corpse_1', pile: null, item: null, index: null, bionic: 'datajack' });
    after(player({ money: 12, items: [LAMP, JACK], corpses: [{ ...corpse, money: 0, bionics: [] }] }));
    expect(lines(0)).toEqual(['Money12', 'Lamp1 kg', 'Datajack0.5 kg']);
    expect(selected()).toBe('Copper wire1.5 kg');
    expect(side(0).querySelector('h3')?.textContent).toBe('You carry 1.5 of 10 kg');
  });

  it('says why a row that will not fit does nothing, and sends nothing', () => {
    opened(player({ corpses: [body({ items: [HEAVY, WIRE] })] }));

    expect(selected()).toContain('Too heavy');
    expect(status()).toBe("It's too heavy. You can carry 9 kg more.");
    expect(side(1).querySelector('li')?.classList.contains('clinic-short')).toBe(true);
    press('Enter');
    (side(1).querySelector('li') as HTMLElement).click();
    expect(sent).toEqual([]);
  });

  it('takes what fits of a stack and says so', () => {
    opened(player({ corpses: [body({ items: [plastic(30)] })] }));

    expect(status()).toBe("Enter to take 18 of 30. The rest won't fit.");
    press('Enter');
    expect(sent).toEqual([{ type: 'take', corpse: 'corpse_1', pile: null, item: 'plastic', index: 0, bionic: null }]);
  });

  it('clicking a row chooses it and takes it', () => {
    opened(player({ corpses: [body({ money: 3, items: [WIRE] })] }));

    (side(1).querySelectorAll('li')[1] as HTMLElement).click();

    expect(selected()).toBe('Copper wire1.5 kg');
    expect(sent).toEqual([{ type: 'take', corpse: 'corpse_1', pile: null, item: 'copper_wire', index: 0, bionic: null }]);
  });

  describe('with two pistols that share an id', () => {
    const pistol = (rounds: number, condition: number): Item => ({ id: 'plastic_pistol', kind: 'weapon', name: 'Plastic pistol', weight: 0.5, material: 'plastic', rounds, capacity: 6, condition, charge: null, on: null });
    const [worn, loaded] = [pistol(0, 0.1), pistol(6, 1)];
    const taking = (index: number, item = 'plastic_pistol') => ({ type: 'take', corpse: 'corpse_1', pile: null, item, index, bionic: null });

    afterEach(() => vi.useRealTimers());

    it('sends one take at a time, and the next for the row under the cursor in the state that follows', () => {
      vi.useFakeTimers();
      opened(player({ corpses: [body({ items: [WIRE, worn, loaded] })] }));

      press('Enter');
      press('ArrowDown');
      press('Enter');
      press('Enter');
      expect(sent).toEqual([taking(0, 'copper_wire')]);

      after(player({ items: [LAMP, WIRE], corpses: [body({ items: [worn, loaded] })] }));
      expect(selected()).toContain('0 of 6 rounds');
      press('ArrowDown');
      press('Enter');
      press('Enter');
      expect(sent).toEqual([taking(0, 'copper_wire'), taking(1)]);

      after(player({ items: [LAMP, WIRE, loaded], corpses: [body({ items: [worn] })] }));
      press('Enter');
      expect(sent.at(-1)).toEqual(taking(0));
    });

    it('takes the row under the cursor in a state that came between frames', () => {
      vi.useFakeTimers();
      opened(player({ corpses: [body({ items: [WIRE, worn, loaded] })] }));
      press('ArrowDown');
      press('ArrowDown');
      expect(selected()).toContain('6 of 6 rounds');

      playerState.latest = state(player({ items: [LAMP, WIRE], corpses: [body({ items: [worn, loaded] })] }));
      press('Enter');

      expect(sent).toEqual([taking(1)]);
    });

    it('waits for what lies there to change, not for a state that only moves hunger or a charge', () => {
      vi.useFakeTimers();
      const corpse = body({ items: [worn, loaded] });
      opened(player({ corpses: [corpse] }));

      press('Enter');
      after(player({ corpses: [corpse], hunger: 0.31 }));
      press('ArrowDown');
      press('Enter');
      expect(sent).toEqual([taking(0)]);

      after(player({ items: [LAMP, worn], corpses: [body({ items: [loaded] })], hunger: 0.31 }));
      press('Enter');
      expect(sent).toEqual([taking(0), taking(0)]);
    });

    it('never sends again a take the server refused, but lets another row go a moment later', () => {
      vi.useFakeTimers();
      const corpse = body({ items: [worn, loaded] });
      opened(player({ corpses: [corpse] }));

      press('Enter');
      vi.advanceTimersByTime(REFUSED_MS);
      after(player({ corpses: [corpse], hunger: 0.32 }));
      press('Enter');
      expect(sent).toEqual([taking(0)]);

      press('ArrowDown');
      press('Enter');
      expect(sent).toEqual([taking(0), taking(1)]);
    });
  });

  it('does not take twice for a held Enter', () => {
    opened(player({ corpses: [body({ money: 3 })] }));

    press('Enter', true);

    expect(sent).toEqual([]);
  });

  it('keeps every key from the game, and what they carry is not chosen', () => {
    opened(player({ corpses: [body({ money: 3, items: [WIRE] })] }));
    const seen = vi.fn();
    parent.addEventListener('keydown', seen);

    for (const key of ['ArrowLeft', 'ArrowRight', 'Tab', 'w']) press(key);

    expect(seen).not.toHaveBeenCalled();
    expect(side(0).querySelector('.clinic-selected')).toBeNull();
    (side(0).querySelector('li') as HTMLElement).click();
    expect(sent).toEqual([]);
  });

  it.each(['Escape', 'e', 'E'])('closes on %s and gives the focus back', (key) => {
    opened(player({ corpses: [body({ money: 3 })] }));

    press(key);

    expect(panel.isOpen).toBe(false);
    expect(document.activeElement).not.toBe(element());
  });

  it('closes once the last thing is taken and the corpse has gone', () => {
    opened(player({ corpses: [body({ items: [WIRE] }), body({ money: 1 }, 'corpse_2')] }));

    after(player({ items: [LAMP, WIRE], corpses: [body({ money: 1 }, 'corpse_2')] }));

    expect(panel.isOpen).toBe(false);
  });

  it('closes once they have left it, on another map or too far', () => {
    const playing = player({ corpses: [body({ money: 1 })] });
    opened(playing);
    after(playing, { ...HERE, x: 66.5 });
    expect(panel.isOpen).toBe(true);
    after(playing, { ...HERE, x: 66.6 });
    expect(panel.isOpen).toBe(false);

    opened(playing);
    after(playing, { ...HERE, map: 'sewers' });
    expect(panel.isOpen).toBe(false);

    opened(playing);
    panel.update(undefined);
    expect(panel.isOpen).toBe(false);
  });

  it('opens on a pile in `left`, follows it down the tile, and closes when none is left', () => {
    const pile: Pile = { at: AT, items: [WIRE], money: 3 };
    const next: Pile = { at: AT, items: [LAMP] };
    opened(player({ items: [], left: [pile, next] }), atPile(pile));
    expect(parent.querySelector('header')?.textContent).toBe('Lying here');
    expect(side(1).querySelector('h3')?.textContent).toBe('On the ground');
    expect(side(0).querySelector('ol')?.dataset.empty).toBe('You carry nothing.');

    press('ArrowDown');
    press('Enter');
    expect(sent).toEqual([{ type: 'take', corpse: null, pile: AT, item: 'copper_wire', index: 0, bionic: null }]);

    after(player({ items: [WIRE], left: [next] }));
    expect(lines(1)).toEqual(['Lamp1 kg']);
    after(player({ items: [WIRE, LAMP] }));
    expect(panel.isOpen).toBe(false);
  });

  it("doesn't open on salvage or a secret lying about, which E picks up", () => {
    const lying: Pile = { at: AT, items: [WIRE] };
    playerState.latest = state(player());

    expect(panel.open(atPile(lying))).toBe(false);
    expect(panel.isOpen).toBe(false);
  });

  it('opens on a corpse holding only what will not fit, and says why', () => {
    opened(player({ corpses: [body({ bionics: ['bionic_legs_3'] })], items: [HEAVY] }));

    expect(selected()).toContain('Too heavy');
    expect(status()).toBe("It's too heavy. You can carry 0.5 kg more.");
  });
});
