import { describe, expect, it, vi } from 'vitest';
import type { Body } from '../net/protocol';
import { dolls } from './assets';
import { FITTED, isPlayerFigure, PlayerBody, playerFigureId } from './bionics';

const whole: Body = {
  legs: 'present',
  vertebra: 'present',
  left_eye: 'present',
  right_eye: 'present',
  left_kidney: 'present',
  right_kidney: 'present',
};

describe('the player’s figure', () => {
  it.each<[Partial<Body>, string]>([
    [{}, 'player'],
    [{ left_kidney: 'sold', right_eye: 'sold' }, 'player'],
    [{ legs: 'hydraulic_legs' }, 'player_legs'],
    [{ legs: 'sprint_legs' }, 'player_legs'],
    [{ legs: 'premium_legs', vertebra: 'datajack' }, 'player_legs_datajack'],
    [{ vertebra: 'datajack' }, 'player_datajack'],
    [{ left_eye: 'infrared_eye' }, 'player_eye'],
    [{ right_eye: 'infrared_eye', legs: 'hydraulic_legs' }, 'player_legs_eye'],
    [{ right_eye: 'infrared_eye', vertebra: 'datajack', legs: 'hydraulic_legs' }, 'player_legs_datajack_eye'],
  ])('with %o fitted is %s', (fitted, id) => {
    expect(playerFigureId({ ...whole, ...fitted })).toBe(id);
  });

  it('is the whole player before the body is known', () => {
    expect(playerFigureId()).toBe('player');
  });

  it('is committed for every combination of bionics, with the same frames and poses', () => {
    const combinations = FITTED.reduce<string[][]>((all, part) => [...all, ...all.map((c) => [...c, part])], [[]]);
    for (const parts of combinations) {
      const body: Body = { ...whole };
      if (parts.includes('hydraulic_legs')) body.legs = 'hydraulic_legs';
      if (parts.includes('datajack')) body.vertebra = 'datajack';
      if (parts.includes('infrared_eye')) body.left_eye = 'infrared_eye';
      const figure = dolls[playerFigureId(body)];
      expect(figure, playerFigureId(body)).toBeDefined();
      expect(Object.keys(figure.frames).sort()).toEqual(Object.keys(dolls.player.frames).sort());
      expect(figure.poses).toEqual(dolls.player.poses);
      expect(figure.height).toBe(dolls.player.height);
    }
  });

  it('tells the player’s figures from the residents’', () => {
    expect(isPlayerFigure('player')).toBe(true);
    expect(isPlayerFigure('player_legs_eye')).toBe(true);
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
    body.set({ ...whole, legs: 'hydraulic_legs' });
    body.set({ ...whole, legs: 'hydraulic_legs', right_eye: 'infrared_eye' });
    stop();
    body.set(whole);

    expect(heard.mock.calls).toEqual([['player_legs'], ['player_legs_eye']]);
    expect(body.figure).toBe('player');
  });
});
