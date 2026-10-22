import { describe, expect, it } from 'vitest';
import { PlayerBody } from '../dolls/bionics';
import { server, type Body } from '../net';
import { dollFor, dolls, mapIds, maps, playerBody } from './assets';

const whole: Body = {
  legs: 'present',
  vertebra: 'present',
  left_eye: 'present',
  right_eye: 'present',
  left_kidney: 'present',
  right_kidney: 'present',
};

describe('maps', () => {
  it('has every street and floor, bundled', () => {
    expect(mapIds).toContain('high_street');
    expect(mapIds).toContain('banyan_row');
    expect(mapIds).toContain('coffee_shop_floor_0');
    expect(mapIds).toContain('house_10_floor_1');
    expect(mapIds).not.toContain('village');
    expect(maps.high_street?.width).toBe(84);
    expect(maps.gallery_floor_2?.properties).toContainEqual({ name: 'view', type: 'string', value: 'side' });
  });
});

describe('dollFor', () => {
  it('is their own doll, or the same resident’s every time for anyone without one', () => {
    expect(dollFor('kofi')).toBe(dolls.kofi);
    expect(dollFor('player')).toBe(dolls.player);
    const stranger = dollFor('wren_abernethy');
    expect(dollFor('wren_abernethy')).toBe(stranger);
    expect(stranger.id).not.toMatch(/^player/);
    expect(Object.values(dolls)).toContain(stranger);
  });

  it('is the player’s with whatever bionics are fitted', () => {
    const body = new PlayerBody();
    expect(dollFor('player', body)).toBe(dolls.player);

    body.set({ ...whole, legs: 'hydraulic_legs', right_eye: 'infrared_eye' });

    expect(dollFor('player', body)).toBe(dolls.player_legs_eye);
    expect(dollFor('kofi', body)).toBe(dolls.kofi);
  });

  it('hears what’s fitted from player_state', () => {
    const player = { money: 0, items: [], carry_limit: 10, hunger: 0, body: { ...whole, vertebra: 'datajack' } };

    server.dispatch(JSON.stringify({ type: 'player_state', player }));

    expect(playerBody.figure).toBe('player_datajack');
    expect(dollFor('player')).toBe(dolls.player_datajack);
    server.dispatch(JSON.stringify({ type: 'player_state', player: { ...player, body: whole } }));
    expect(dollFor('player')).toBe(dolls.player);
  });
});
