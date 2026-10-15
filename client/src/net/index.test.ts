import { expect, it, vi } from 'vitest';
import { server, type LineMessage } from '.';

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
