import { describe, expect, it, vi } from 'vitest';
import type { Body } from '../net/protocol';
import { dolls } from './assets';
import { isPlayerFigure, PlayerBody, playerFigureId } from './bionics';

const whole: Body = {
  legs: 'present',
  vertebra: 'present',
  left_eye: 'present',
  right_eye: 'present',
  left_kidney: 'present',
  right_kidney: 'present',
  stomach: 'present',
  feet: 'present',
};

describe('the player’s figure', () => {
  it.each<[Partial<Body>, string]>([
    [{}, 'player'],
    [{ left_kidney: 'sold', right_eye: 'sold' }, 'player'],
    [{ stomach: 'power_cell' }, 'player'],
    [{ legs: 'bionic_legs_3', vertebra: 'datajack' }, 'player_bionic_legs_datajack'],
    [{ vertebra: 'datajack' }, 'player_datajack'],
    [{ left_eye: 'infrared_eye' }, 'player_eye'],
    [{ right_eye: 'infrared_eye', feet: 'spring_feet' }, 'player_feet_eye'],
    [{ right_eye: 'infrared_eye', vertebra: 'datajack', legs: 'bionic_legs' }, 'player_bionic_legs_datajack_eye'],
    [{ legs: 'bionic_legs', stomach: 'power_cell' }, 'player_bionic_legs'],
    [{ legs: 'bionic_legs_3', stomach: 'power_cell_2' }, 'player_bionic_legs'],
    [{ feet: 'spring_feet_2' }, 'player_feet'],
    [{ legs: 'bionic_legs_2', feet: 'spring_feet', left_eye: 'infrared_eye' }, 'player_bionic_legs_feet_eye'],
  ])('with %o fitted is %s', (fitted, id) => {
    expect(playerFigureId({ ...whole, ...fitted })).toBe(id);
  });

  it('is the whole player before the body is known', () => {
    expect(playerFigureId()).toBe('player');
  });

  it('is committed for every body, with the same frames and poses', () => {
    const bodies: Body[] = [];
    for (const legs of ['present', 'bionic_legs', 'bionic_legs_3'] as const)
      for (const feet of ['present', 'spring_feet', 'spring_feet_2'] as const)
        for (const vertebra of ['present', 'datajack'] as const)
          for (const left_eye of ['present', 'infrared_eye'] as const)
            bodies.push({ ...whole, legs, feet, vertebra, left_eye, stomach: 'power_cell' });
    for (const body of bodies) {
      const figure = dolls[playerFigureId(body)];
      expect(figure, playerFigureId(body)).toBeDefined();
      expect(Object.keys(figure.frames).sort()).toEqual(Object.keys(dolls.player.frames).sort());
      expect(figure.poses).toEqual(dolls.player.poses);
      expect(figure.height).toBe(dolls.player.height);
    }
    expect(Object.keys(dolls).filter(isPlayerFigure).sort()).toEqual([...new Set(bodies.map(playerFigureId))].sort());
  });

  it('tells the player’s figures from the residents’', () => {
    expect(isPlayerFigure('player')).toBe(true);
    expect(isPlayerFigure('player_feet_eye')).toBe(true);
    expect(isPlayerFigure('player_bionic_legs_feet')).toBe(true);
    expect(isPlayerFigure('priya')).toBe(false);
    expect(isPlayerFigure(undefined)).toBe(false);
  });
});

describe('PlayerBody', () => {
  it('says when the figure changes, and only then', () => {
    const body = new PlayerBody();
    const heard = vi.fn();
    const stop = body.onChange(heard);

    body.set(whole);
    body.set({ ...whole, left_kidney: 'sold' });
    body.set({ ...whole, stomach: 'power_cell' });
    body.set({ ...whole, stomach: 'power_cell', legs: 'bionic_legs' });
    body.set({ ...whole, stomach: 'power_cell', legs: 'bionic_legs_2' });
    body.set({ ...whole, stomach: 'power_cell', legs: 'bionic_legs_2', feet: 'spring_feet' });
    stop();
    body.set(whole);

    expect(heard.mock.calls).toEqual([['player_bionic_legs'], ['player_bionic_legs_feet']]);
    expect(body.figure).toBe('player');
  });
});
