import { afterEach, describe, expect, it, vi } from 'vitest';
import { drawnImage, fakeScene } from '../dolls/phaser.fixture';
import type { Body } from '../net';
import { dolls, playerBody } from '../world/assets';
import { emptyDrawn } from './motion';
import { BED_M } from './poses';
import { SideDoll } from './side-doll';

vi.mock('phaser', () => import('../dolls/phaser.fixture'));

const whole: Body = {
  legs: 'present',
  vertebra: 'present',
  left_eye: 'present',
  right_eye: 'present',
  left_kidney: 'present',
  right_kidney: 'present',
};
const scene = () => fakeScene(Object.keys(dolls).map((id) => `figure-${id}`));

afterEach(() => playerBody.set(whole));

describe('the side view’s player', () => {
  it('wears the figure for each bionic fitted', async () => {
    const doll = new SideDoll(scene(), dolls.player, 'figure-player');

    playerBody.set({ ...whole, legs: 'bionic_legs' });
    await vi.waitFor(() => expect(doll.figure).toBe(dolls.player_bionic_legs));
    playerBody.set({ ...whole, legs: 'bionic_legs', left_eye: 'infrared_eye' });

    await vi.waitFor(() => expect(doll.figure).toBe(dolls.player_bionic_legs_eye));
    expect(drawnImage(doll).key).toBe('figure-player_bionic_legs_eye');
  });

  it('catches up with a bionic fitted while its first atlas loaded', async () => {
    const picked = dolls.player;
    playerBody.set({ ...whole, vertebra: 'datajack' });

    const doll = new SideDoll(scene(), picked, 'figure-player');

    await vi.waitFor(() => expect(doll.figure).toBe(dolls.player_datajack));
  });

  it('stops following once it’s gone', async () => {
    const doll = new SideDoll(scene(), dolls.player, 'figure-player');
    doll.destroy();

    playerBody.set({ ...whole, legs: 'bionic_legs' });
    await Promise.resolve();

    expect(doll.figure).toBe(dolls.player);
  });

  it('leaves a resident’s figure alone', async () => {
    const doll = new SideDoll(scene(), dolls.kofi, 'figure-kofi');

    playerBody.set({ ...whole, legs: 'bionic_legs' });
    await Promise.resolve();

    expect(doll.figure).toBe(dolls.kofi);
  });
});

describe('a resident in bed', () => {
  const bed = { height: BED_M, along: 0.55 };

  it('sits on its edge, then lies on it, unmirrored, and stands once out of it', () => {
    const doll = new SideDoll(scene(), dolls.ingrid, 'figure-ingrid');
    const drawn = { ...emptyDrawn(), pose: 'sleeping' as const, facing: 'west' as const };

    doll.show({ ...drawn, bed: 0.3 }, 0xffffff, 0, bed);
    expect(drawnImage(doll)).toMatchObject({ frame: dolls.ingrid.poses.sit[0], flipX: false });
    doll.show({ ...drawn, bed: 1 }, 0xffffff, 0, bed);
    expect(drawnImage(doll)).toMatchObject({ frame: 'lie', flipX: false });
    doll.show({ ...drawn, pose: 'standing', bed: 0 }, 0xffffff, 0, bed);
    expect(drawnImage(doll)).toMatchObject({ frame: dolls.ingrid.poses.stand[0], flipX: true });
  });
});
