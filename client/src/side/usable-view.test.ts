import { afterEach, describe, expect, it, vi } from 'vitest';
import { playerState, type Corpse, type Pile, type PlayerStateMessage } from '../net';
import { scenery, village } from './content';
import { TILE } from './layout';
import type { Content, StreetView } from './street-view';
import type { SideTextures } from './textures';
import { UsableView } from './usable-view';

vi.mock('phaser', () => ({ default: {} }));

const FRONT = { map: 'high_street', x: 10, y: 15 };
const BEYOND = { map: 'high_street', x: 30, y: 15 };
const WIRE = { id: 'copper_wire', kind: 'salvage', name: 'Copper wire', weight: 1.5, charge: null, on: null } as const;
const body = (id: string, at: typeof FRONT): Corpse => ({ id, owner: 'player', at, money: 1, items: [], bionics: [] });
const pile = (at: typeof FRONT): Pile => ({ at, items: [WIRE] });

function image() {
  const self: Record<string, unknown> = { height: 1, visible: true };
  for (const method of ['setOrigin', 'setDepth', 'setScale', 'setTint', 'destroy', 'setAlpha']) self[method] = () => self;
  self.setVisible = (visible: boolean) => {
    self.visible = visible;
    return self;
  };
  return self;
}

/** A street with a real map, its front off over tiles 2 to 18 while `open`, as `StreetView.ghost` has it. */
function street(open: boolean): StreetView {
  const map = village.map('high_street')!;
  return {
    map,
    tints: { colours: { inside: 0, ground: 0 } },
    isOpen: (name: string | undefined) => open && name === 'maker_space',
    ghost: (x: number) => (open && x >= 2 * TILE && x <= 18 * TILE ? 0 : 1),
  } as unknown as StreetView;
}

function drawnAll(open: boolean) {
  const scene = { add: { image }, textures: { exists: () => true } } as unknown as Phaser.Scene;
  const textures = { key: (name: string) => name } as unknown as SideTextures;
  const view = new UsableView(scene, textures);
  view.update({ village, scenery } as Content, street(open), undefined, 0);
  return view.drawn().filter(({ id }) => /^(corpse|pile):/.test(id)).map(({ id, shown }) => [id, shown]);
}

describe('UsableView', () => {
  afterEach(() => {
    delete playerState.latest;
  });

  it('leaves out a body or pile on the street while the front over it is off, and not one beyond that front', () => {
    const player = { items: [], money: 0, left: [pile(FRONT), pile(BEYOND)], corpses: [body('front', FRONT), body('beyond', BEYOND)] };
    playerState.latest = { player } as unknown as PlayerStateMessage;

    expect(drawnAll(false)).toEqual(expect.arrayContaining([['corpse:front', true], ['pile:high_street:10,15', true], ['corpse:beyond', true], ['pile:high_street:30,15', true]]));
    expect(drawnAll(true)).toEqual(expect.arrayContaining([['corpse:front', false], ['pile:high_street:10,15', false], ['corpse:beyond', true], ['pile:high_street:30,15', true]]));
  });
});
