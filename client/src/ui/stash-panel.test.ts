// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { playerState, type Item, type Player, type PlayerStateMessage, type Position, type StashMessage } from '../net';
import { fitting, lockersAt, note, rowsOf, StashPanel } from './stash-panel';

vi.mock('./icons', () => ({ iconUrl: (id: string) => (id === 'copper_wire' ? '/icons/copper_wire.webp' : undefined) }));
vi.mock('../world/interactables', () => ({
  interactableAt: (map: string, position: { x: number } | undefined) =>
    map !== 'maker_space_floor_2'
      ? undefined
      : position?.x === 7
        ? { id: 'lockers', kind: 'machine', label: 'Lockers', prompt: 'Use the lockers' }
        : position?.x === 9
          ? { id: 'maker_space_shelf', kind: 'searchable', label: 'Shelf', prompt: 'Search the shelf' }
          : undefined,
}));

const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 1, on: false };
const plastic = (amount: number, weight = 0.5): Item => ({ id: 'plastic', kind: 'material', name: 'Plastic', weight, amount, material: 'plastic', charge: null, on: null });
const rounds = (amount: number, weight = 0.1): Item => ({ id: 'plastic_rounds', kind: 'rounds', name: 'Plastic rounds', weight, amount, material: 'plastic', charge: null, on: null });
const pistol = (loaded: number, condition: number): Item => ({
  id: 'plastic_pistol',
  kind: 'weapon',
  name: 'Plastic pistol',
  weight: 0.5,
  material: 'plastic',
  rounds: loaded,
  capacity: 6,
  condition,
  charge: null,
  on: null,
});
const AT_THE_LOCKERS: Position = { x: 7, y: 2, map: 'maker_space_floor_2' };
const AT_THE_SHELF: Position = { x: 9, y: 2, map: 'maker_space_floor_2' };
const player = (items: Item[], stash?: Player['stash'], carry_limit = 15): Player => ({ items, money: 0, carry_limit, ...(stash && { stash }) }) as unknown as Player;
const state = (playing: Player) => ({ player: playing }) as PlayerStateMessage;

describe('fitting', () => {
  it.each([
    ['a whole stack with room', rounds(6), 1, 6],
    ['3 rounds where 0.3 / 0.1 falls short of 3', rounds(6), 0.3, 3],
    ['no rounds in too little room', rounds(6), 0.05, 0],
    ['no rounds with no room', rounds(6), -1, 0],
    ['a part of a material', plastic(6, 0.1), 0.3, 3],
    ['a float sum whole, leaving no dust', plastic(0.1 + 0.2, 1), 0.3, 0.1 + 0.2],
    ['nothing of a material for a rounding error of room', plastic(2, 1), 1e-12, 0],
    ['what weighs nothing, even with no room', plastic(2, 0), -1, 2],
    ['a single thing that just fits', WIRE, 1.5 - 1e-12, 1],
    ["a single thing that doesn't", WIRE, 1.4, 0],
  ])('%s', (_, item, room, fits) => {
    expect(fitting(item, room)).toBe(fits);
  });
});

describe('rowsOf', () => {
  it('has a row per id, counting all of it, with what would move of the first', () => {
    const rows = rowsOf([pistol(2, 0.4), plastic(4), pistol(6, 1)], 1);

    expect(rows.map(({ id, count, load, moves }) => [id, count, load, moves])).toEqual([
      ['plastic_pistol', 2, 1, 1],
      ['plastic', 4, 2, 2],
    ]);
    expect(rows[0]!.first.rounds).toBe(2);
  });
});

describe('note', () => {
  it('says what Enter will do, how much of a stack, and why it can do nothing', () => {
    expect(note(rowsOf([WIRE], 5)[0], 'store', 5)).toBe('Enter to store it.');
    expect(note(rowsOf([WIRE], 5)[0], 'take', 5)).toBe('Enter to take it.');
    expect(note(rowsOf([plastic(10)], 2)[0], 'store', 2)).toBe("Enter to store 4 of 10. The rest won't fit.");
    expect(note(rowsOf([WIRE], 1)[0], 'store', 1)).toBe("It won't fit. The lockers have 1 kg left.");
    expect(note(rowsOf([WIRE], 0.5)[0], 'take', 0.5)).toBe("It's too heavy. You can carry 0.5 kg more.");
    expect(note(rowsOf([WIRE], -1)[0], 'take', -1)).toBe("It's too heavy. You can carry 0 kg more.");
    expect(note(undefined, 'store', 20)).toBe("You're carrying nothing to store.");
    expect(note(undefined, 'take', 15)).toBe('There is nothing in the lockers to take.');
  });
});

describe('lockersAt', () => {
  it("is only the lockers' stand tile", () => {
    expect(lockersAt(AT_THE_LOCKERS)?.id).toBe('lockers');
    expect(lockersAt(AT_THE_SHELF)).toBeUndefined();
    expect(lockersAt(undefined)).toBeUndefined();
  });
});

describe('StashPanel', () => {
  let parent: HTMLElement;
  let sent: StashMessage[];
  let panel: StashPanel;

  const element = () => parent.querySelector<HTMLElement>('.stash-panel')!;
  const side = (index: number) => parent.querySelectorAll<HTMLElement>('.clinic-side')[index]!;
  const lines = (index: number) => [...side(index).querySelectorAll('li')].map((line) => line.textContent);
  const selected = () => parent.querySelector('.clinic-selected')?.textContent;
  const status = () => parent.querySelector('footer p')?.textContent;
  const press = (key: string) => {
    const event = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
    element().dispatchEvent(event);
    return event;
  };
  const opened = (playing: Player) => {
    playerState.latest = state(playing);
    expect(panel.use(AT_THE_LOCKERS, false)).toBe(true);
  };

  beforeEach(() => {
    parent = document.body.appendChild(document.createElement('div'));
    sent = [];
    panel = new StashPanel(parent, (message) => sent.push(message));
  });

  afterEach(() => {
    parent.remove();
    delete playerState.latest;
  });

  it('is no section.clinic and has no hint of its own, so the scene keeps its queries', () => {
    expect(parent.querySelector('section.clinic')).toBeNull();
    expect(parent.querySelector('.counter-hint')).toBeNull();
  });

  it('opens at the lockers beside what they carry, on what they carry', () => {
    opened(player([LAMP, WIRE], { items: [plastic(4)], limit: 20 }));

    expect(panel.isOpen).toBe(true);
    expect(document.activeElement).toBe(element());
    expect(parent.querySelector('header b')?.textContent).toBe('Lockers');
    expect(side(0).querySelector('h3')?.textContent).toBe('You carry 2.5 of 15 kg');
    expect(side(1).querySelector('h3')?.textContent).toBe('In the lockers 2 of 20 kg');
    expect(lines(0)).toEqual(['Lamp1 kg', 'Copper wire1.5 kg']);
    expect(lines(1)).toEqual(['Plastic ×42 kg']);
    expect(selected()).toBe('Lamp1 kg');
    expect(side(0).classList.contains('clinic-active')).toBe(true);
    expect(status()).toBe('Enter to store it.');
    expect(side(0).querySelector('li:nth-child(2) img')?.getAttribute('src')).toBe('/icons/copper_wire.webp');
    expect(side(0).querySelector('li .clinic-blank')).not.toBeNull();
  });

  it('reads an empty stash, left out of the player, as empty at its starting limit', () => {
    opened(player([LAMP]));

    expect(side(1).querySelector('h3')?.textContent).toBe('In the lockers 0 of 20 kg');
    expect(lines(1)).toEqual([]);
  });

  it('opens only on the lockers, and not where E does something else', () => {
    playerState.latest = state(player([LAMP]));

    expect(panel.use(AT_THE_SHELF, false)).toBe(false);
    expect(panel.use(AT_THE_LOCKERS, true)).toBe(false);
    expect(panel.isOpen).toBe(false);
    expect(panel.prompt(AT_THE_SHELF, false)).toBeUndefined();
    expect(panel.prompt(AT_THE_LOCKERS, true)).toBeUndefined();
    expect(panel.prompt(AT_THE_LOCKERS, false)?.id).toBe('lockers');
    panel.use(AT_THE_LOCKERS, false);
    expect(panel.prompt(AT_THE_LOCKERS, false)).toBeUndefined();
  });

  it('needs a player_state to open', () => {
    expect(panel.use(AT_THE_LOCKERS, false)).toBe(false);
  });

  it('stores what is chosen on Enter, and takes from the other side', () => {
    opened(player([LAMP, WIRE], { items: [plastic(4)], limit: 20 }));

    press('ArrowDown');
    expect(selected()).toBe('Copper wire1.5 kg');
    press('Enter');
    expect(sent).toEqual([{ type: 'stash', item: 'copper_wire', action: 'store' }]);

    press('ArrowRight');
    expect(side(1).classList.contains('clinic-active')).toBe(true);
    expect(selected()).toBe('Plastic ×42 kg');
    expect(status()).toBe('Enter to take it.');
    press(' ');
    expect(sent.at(-1)).toEqual({ type: 'stash', item: 'plastic', action: 'take' });
  });

  it("sends nothing for what wouldn't fit at all, and says why", () => {
    opened(player([WIRE], { items: [plastic(39)], limit: 20 }));

    expect(status()).toBe("It won't fit. The lockers have 0.5 kg left.");
    expect(parent.querySelector('.clinic-short')).not.toBeNull();
    press('Enter');
    expect(sent).toEqual([]);
  });

  it('moves part of a stack that only part of fits', () => {
    opened(player([plastic(10)], { items: [], limit: 2 }));

    expect(status()).toBe("Enter to store 4 of 10. The rest won't fit.");
    press('Enter');
    expect(sent).toEqual([{ type: 'stash', item: 'plastic', action: 'store' }]);
  });

  it('shows the rounds and condition of the weapon that moves next', () => {
    opened(player([], { items: [pistol(2, 0.4), pistol(6, 1)], limit: 20 }));

    expect(lines(1)).toEqual(['Plastic pistol ×22 of 6 rounds, 40%1 kg']);
  });

  it('keeps the choice on its row as the state changes, and on what takes a moved row’s place', () => {
    opened(player([LAMP, WIRE, plastic(1)]));
    press('ArrowDown');

    playerState.latest = state(player([WIRE, plastic(1)], { items: [LAMP], limit: 20 }));
    panel.update(AT_THE_LOCKERS);
    expect(selected()).toBe('Copper wire1.5 kg');

    playerState.latest = state(player([plastic(1)], { items: [LAMP, WIRE], limit: 20 }));
    panel.update(AT_THE_LOCKERS);
    expect(selected()).toBe('Plastic0.5 kg');
    expect(lines(1)).toEqual(['Lamp1 kg', 'Copper wire1.5 kg']);
  });

  it('wraps ↑ ↓ and clamps across to a shorter side', () => {
    opened(player([LAMP, WIRE, plastic(1)], { items: [plastic(2)], limit: 20 }));

    press('ArrowUp');
    expect(selected()).toBe('Plastic0.5 kg');
    press('ArrowRight');
    expect(selected()).toBe('Plastic ×21 kg');
    press('ArrowRight');
    press('ArrowLeft');
    expect(selected()).toBe('Lamp1 kg');
  });

  it('acts on a click, on either side', () => {
    opened(player([LAMP], { items: [plastic(2)], limit: 20 }));

    side(1).querySelector('li')!.click();

    expect(sent).toEqual([{ type: 'stash', item: 'plastic', action: 'take' }]);
    expect(side(1).classList.contains('clinic-active')).toBe(true);
  });

  it('keeps its keys from the game, and closes on Esc or E', () => {
    opened(player([LAMP]));
    let reached = 0;
    const onWindow = () => reached++;
    window.addEventListener('keydown', onWindow);

    expect(press('ArrowLeft').defaultPrevented).toBe(true);
    press('Escape');
    expect(panel.isOpen).toBe(false);
    panel.use(AT_THE_LOCKERS, false);
    press('e');
    expect(panel.isOpen).toBe(false);
    expect(reached).toBe(0);
    window.removeEventListener('keydown', onWindow);
  });

  it('closes once they leave the lockers', () => {
    opened(player([LAMP]));

    panel.update(AT_THE_SHELF);

    expect(panel.isOpen).toBe(false);
  });

  it('opens on what they carry again, however it was left', () => {
    opened(player([LAMP, WIRE], { items: [plastic(2)], limit: 20 }));
    press('ArrowRight');
    press('Escape');

    panel.use(AT_THE_LOCKERS, false);

    expect(selected()).toBe('Lamp1 kg');
  });
});
