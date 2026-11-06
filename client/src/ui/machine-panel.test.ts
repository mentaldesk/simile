// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { playerState, server, type Item, type Machine, type Player, type PlayerStateMessage, type Position, type Product } from '../net';
import { carried, counted, machineAt, machines, MachinePanel, note, resetMachines, rowsOf, type Action, type Row } from './machine-panel';

vi.mock('./icons', () => ({ iconUrl: (id: string) => (id === 'copper_wire' ? '/icons/copper_wire.webp' : undefined) }));
vi.mock('../world/interactables', () => ({
  interactableAt: (map: string, position: { x: number } | undefined) =>
    map === 'maker_space_floor_0' && position?.x === 9 ? { id: 'printer_3d', kind: 'machine', label: '3D printer', prompt: 'Use the 3D printer' } : undefined,
}));

const WIRE: Item = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null };
const SHEET: Item = { id: 'metal_sheet', kind: 'part', name: 'Metal sheet', weight: 2, charge: null, on: null };
const ACTUATOR: Item = { id: 'linear_actuator', kind: 'part', name: 'Linear actuator', weight: 1, charge: null, on: null };
const PLASTIC: Item = { id: 'plastic', kind: 'material', name: 'Plastic', weight: 0.5, amount: 8, material: 'plastic', charge: null, on: null };
const LAMP: Item = { id: 'lamp', kind: 'lamp', name: 'Lamp', weight: 1, charge: 1, on: false };
const PISTOL: Product = { item: { id: 'pistol', kind: 'weapon', name: 'Plastic pistol', weight: 1, charge: null, on: null }, uses: 'plastic', cost: 6 };
const ROUNDS: Product = {
  item: { id: 'rounds', kind: 'rounds', name: 'Rounds', weight: 0.01, amount: 6, charge: null, on: null },
  uses: 'plastic',
  cost: 2,
};
const BROKEN: Machine = { id: 'printer_3d', kind: 'printer', state: 'broken', parts: { metal_sheet: 1, linear_actuator: 1, copper_wire: 2 }, makes: [] };
const WORKING: Machine = { id: 'printer_3d', kind: 'printer', state: 'working', parts: {}, makes: [PISTOL, ROUNDS] };
const EMPTY: Machine = { ...WORKING, makes: [] };
const AT_THE_PRINTER: Position = { x: 9, y: 2, map: 'maker_space_floor_0' };
const player = (items: Item[]): Player => ({ items, money: 0, carry_limit: 20 }) as unknown as Player;

const rowNames = (rows: readonly Row[]) => rows.map(({ name }) => name);

describe('rowsOf', () => {
  it('lists each part of a broken machine with how many they have, then repairing it', () => {
    const rows = rowsOf(BROKEN, [WIRE, LAMP, SHEET]);

    expect(rows.filter((row) => row.kind === 'part').map((row) => (row.kind === 'part' ? [row.name, row.have, row.count] : []))).toEqual([
      ['Metal sheet', 1, 1],
      ['Linear actuator', 0, 1],
      ['Copper wire', 1, 2],
    ]);
    expect(rows.at(-1)).toEqual({ kind: 'repair', id: 'repair', name: 'Repair it', short: true });
  });

  it('can repair once they have every part', () => {
    expect(rowsOf(BROKEN, [SHEET, ACTUATOR, WIRE, WIRE]).at(-1)).toMatchObject({ kind: 'repair', short: false });
  });

  it('lists what a working machine offers against the material they carry', () => {
    const rows = rowsOf(WORKING, [{ ...PLASTIC, amount: 3 }]);

    expect(rowNames(rows)).toEqual(['Plastic pistol', 'Rounds ×6']);
    expect(rows[0]).toMatchObject({ kind: 'make', have: 3, short: true });
    expect(rows[1]).toMatchObject({ kind: 'make', have: 3, short: false });
  });

  it('makes from scrap with any scrap at all, since it takes all they carry', () => {
    const recycler: Machine = { id: 'recycler', kind: 'recycler', state: 'working', parts: {}, makes: [{ item: PLASTIC, uses: 'scrap', cost: 1 }] };

    const [some] = rowsOf(recycler, [{ ...WIRE, weight: 0.5 }]);
    expect(some).toMatchObject({ have: 0.5, short: false });
    expect(counted(some)).toBe('0.5 kg');

    const none = rowsOf(recycler, [SHEET]);
    expect(none[0]).toMatchObject({ have: 0, short: true });
    expect(note(none[0], none)).toBe("It takes scrap, and you're carrying none.");
  });

  it('offers nothing while broken, however much they carry', () => {
    expect(rowsOf(BROKEN, [PLASTIC]).some(({ kind }) => kind === 'make')).toBe(false);
  });
});

describe('carried', () => {
  it('adds up a material by amount', () => {
    expect(carried('plastic', [PLASTIC, { ...PLASTIC, amount: 1.5 }, WIRE])).toBe(9.5);
  });

  it('weighs scrap as all their salvage and nothing else', () => {
    expect(carried('scrap', [WIRE, WIRE, SHEET, PLASTIC, LAMP])).toBe(3);
  });
});

describe('note', () => {
  it('names the first part they are short of', () => {
    const rows = rowsOf(BROKEN, [SHEET, ACTUATOR, WIRE]);

    expect(note(rows.at(-1), rows)).toBe('It needs 2 copper wire, and you have 1.');
  });

  it('says what Enter does, or what an offer takes', () => {
    const fixable = rowsOf(BROKEN, [SHEET, ACTUATOR, WIRE, WIRE]);
    const offers = rowsOf(WORKING, [{ ...PLASTIC, amount: 3 }]);

    expect(note(fixable.at(-1), fixable)).toBe('Enter to repair it. It uses up these parts.');
    expect(note(offers[0], offers)).toBe('It takes 6 plastic, and you have 3.');
    expect(note(offers[1], offers)).toBe('Enter to make it.');
    expect(note(undefined, [])).toBe('It has nothing to offer yet.');
  });
});

describe('the machines', () => {
  afterEach(() => resetMachines());

  it('finds one only on its stand tile', () => {
    resetMachines([BROKEN]);

    expect(machineAt(AT_THE_PRINTER)?.machine).toBe(BROKEN);
    expect(machineAt(AT_THE_PRINTER)?.interactable.label).toBe('3D printer');
    expect(machineAt({ ...AT_THE_PRINTER, x: 8 })).toBeUndefined();
    expect(machineAt(undefined)).toBeUndefined();
  });

  it('follows the snapshot and machine_changed', () => {
    const emit = (server as unknown as { emit: (event: string, message: unknown) => void }).emit.bind(server);

    emit('snapshot', { machines: [BROKEN] });
    expect(machines.get('printer_3d')).toBe(BROKEN);

    emit('machine_changed', { machine: WORKING });
    expect(machines.get('printer_3d')).toBe(WORKING);

    emit('snapshot', {});
    expect(machines.size).toBe(0);
  });
});

describe('MachinePanel', () => {
  let parent: HTMLElement;
  let sent: Action[];
  let panel: MachinePanel;

  const element = () => parent.querySelector<HTMLElement>('.machine-panel')!;
  const lines = () => [...parent.querySelectorAll('li')].map((line) => line.textContent);
  const press = (key: string) => element().dispatchEvent(new KeyboardEvent('keydown', { key, bubbles: true }));

  beforeEach(() => {
    parent = document.body.appendChild(document.createElement('div'));
    sent = [];
    panel = new MachinePanel(parent, (action) => sent.push(action));
    playerState.latest = { player: player([SHEET, ACTUATOR, WIRE]) } as PlayerStateMessage;
    resetMachines([BROKEN]);
  });

  afterEach(() => {
    parent.remove();
    resetMachines();
    delete playerState.latest;
  });

  it('opens at a broken machine showing each part with how many they have', () => {
    expect(panel.use(AT_THE_PRINTER, false)).toBe(true);

    expect(panel.isOpen).toBe(true);
    expect(parent.querySelector('header b')?.textContent).toBe('3D printer');
    expect(parent.querySelector('.clinic-money')?.textContent).toBe('Broken');
    expect(lines()).toEqual(['Metal sheet1/1', 'Linear actuator1/1', 'Copper wire1/2', 'Repair it']);
    expect(parent.querySelector('.clinic-selected')?.textContent).toBe('Repair it');
  });

  it("doesn't open away from a machine, or where E does something else", () => {
    expect(panel.use({ ...AT_THE_PRINTER, x: 8 }, false)).toBe(false);
    expect(panel.use(AT_THE_PRINTER, true)).toBe(false);
    expect(panel.isOpen).toBe(false);
  });

  it('sends nothing until they have every part', () => {
    panel.use(AT_THE_PRINTER, false);

    press('Enter');
    expect(sent).toEqual([]);
    expect(parent.querySelector('footer p')?.textContent).toBe('It needs 2 copper wire, and you have 1.');

    playerState.latest = { player: player([SHEET, ACTUATOR, WIRE, WIRE]) } as PlayerStateMessage;
    panel.update(AT_THE_PRINTER);
    press('Enter');

    expect(sent).toEqual([{ type: 'repair', machine: 'printer_3d' }]);
  });

  it('shows what it offers once repaired, and makes the one chosen', () => {
    playerState.latest = { player: player([PLASTIC]) } as PlayerStateMessage;
    panel.use(AT_THE_PRINTER, false);
    machines.set(WORKING.id, WORKING);
    panel.update(AT_THE_PRINTER);

    expect(parent.querySelector('.clinic-money')?.textContent).toBe('Working');
    expect(lines()).toEqual(['Plastic pistol8/6', 'Rounds ×68/2']);

    press('ArrowDown');
    press('Enter');

    expect(sent).toEqual([{ type: 'make', machine: 'printer_3d', item: 'rounds' }]);
  });

  it('says so while a working machine has nothing to make', () => {
    resetMachines([EMPTY]);
    panel.use(AT_THE_PRINTER, false);

    expect(lines()).toEqual([]);
    expect(parent.querySelector('footer p')?.textContent).toBe('It has nothing to offer yet.');
    press('Enter');
    expect(sent).toEqual([]);
  });

  it('keeps the chosen row as what they carry changes', () => {
    resetMachines([WORKING]);
    playerState.latest = { player: player([PLASTIC]) } as PlayerStateMessage;
    panel.use(AT_THE_PRINTER, false);
    press('ArrowDown');

    playerState.latest = { player: player([{ ...PLASTIC, amount: 5 }]) } as PlayerStateMessage;
    panel.update(AT_THE_PRINTER);

    expect(parent.querySelector('.clinic-selected')?.textContent).toBe('Rounds ×65/2');
  });

  it('closes on Escape, on E, and once they leave', () => {
    panel.use(AT_THE_PRINTER, false);
    press('Escape');
    expect(panel.isOpen).toBe(false);

    panel.use(AT_THE_PRINTER, false);
    press('e');
    expect(panel.isOpen).toBe(false);

    panel.use(AT_THE_PRINTER, false);
    panel.update({ ...AT_THE_PRINTER, x: 8 });
    expect(panel.isOpen).toBe(false);
  });

  it("keeps its keys from the game's", () => {
    const heard = vi.fn();
    window.addEventListener('keydown', heard);
    panel.use(AT_THE_PRINTER, false);

    press('ArrowDown');

    window.removeEventListener('keydown', heard);
    expect(heard).not.toHaveBeenCalled();
  });

  it("prompts at a machine, but not while E does something else or it's open", () => {
    expect(panel.prompt(AT_THE_PRINTER, false)?.id).toBe('printer_3d');
    expect(panel.prompt({ ...AT_THE_PRINTER, x: 8 }, false)).toBeUndefined();
    expect(panel.prompt(AT_THE_PRINTER, true)).toBeUndefined();

    panel.use(AT_THE_PRINTER, false);
    expect(panel.prompt(AT_THE_PRINTER, false)).toBeUndefined();
  });

  it("leaves the first clinic panel and the only prompt on the page to the clinic's and the scene's", () => {
    expect(parent.querySelector('section.clinic')).toBeNull();
    expect(parent.querySelector('.counter-hint')).toBeNull();
  });

  it('draws each part with its icon, or a blank frame until one is painted', () => {
    panel.use(AT_THE_PRINTER, false);

    const [sheet, , wire] = [...parent.querySelectorAll('li')];
    expect(sheet.querySelector('.clinic-blank')).not.toBeNull();
    expect(wire.querySelector('img')?.getAttribute('src')).toBe('/icons/copper_wire.webp');
  });
});
