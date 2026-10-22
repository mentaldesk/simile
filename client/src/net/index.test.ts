import { expect, it, vi } from 'vitest';
import { playerState, server, type LineMessage, type PlayerStateMessage } from '.';

const line: LineMessage = {
  type: 'line',
  line: {
    id: 1,
    conversation_id: 'conv_1',
    speaker: 'mei',
    text: 'Morning!',
    timestamp: '2026-03-14T08:05:00Z',
    duration: 1.2,
  },
  voiced: false,
};

const hungry: PlayerStateMessage = {
  type: 'player_state',
  player: {
    money: 4,
    items: [],
    carry_limit: 10,
    body: {
      legs: 'present',
      vertebra: 'present',
      left_eye: 'present',
      right_eye: 'present',
      left_kidney: 'present',
      right_kidney: 'present',
    },
    hunger: 0.6,
  },
  meal: { place: 'noodle_bar', name: 'Golden Bowl Noodles', price: 10 },
};

it('imports in tests without connecting', () => {
  expect(server.send({ type: 'player_move', position: { x: 1, y: 2 } })).toBe(false);
});

it('lets tests feed in messages and spy on what is sent', () => {
  const lines = vi.fn();
  const unsubscribe = server.on('line', lines);
  const send = vi.spyOn(server, 'send');

  server.dispatch(JSON.stringify(line));
  server.send({ type: 'player_say', text: 'Hi', target: 'mei' });

  expect(lines).toHaveBeenCalledWith(line);
  expect(send).toHaveBeenCalledWith({ type: 'player_say', text: 'Hi', target: 'mei' });
  unsubscribe();
  send.mockRestore();
});

it('keeps the last player_state for scenes that start later', () => {
  server.dispatch(JSON.stringify(hungry));
  expect(playerState.latest).toEqual(hungry);

  server.dispatch(JSON.stringify({ ...hungry, meal: undefined, player: { ...hungry.player, hunger: 0.61 } }));

  expect(playerState.latest?.player.hunger).toBe(0.61);
  expect(playerState.latest?.meal).toBeUndefined();
});
