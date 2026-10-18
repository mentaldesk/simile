import { expect, it, vi } from 'vitest';
import { ServerApi } from './api';

const reply = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });

it('posts a new world as JSON', async () => {
  const fetcher = vi.fn(async () => reply(201, { name: 'w' }));
  const asked = { count: 2, picks: ['ada_jones'], pins: [] };

  expect(await new ServerApi(fetcher).create(asked)).toEqual({ name: 'w' });
  expect(fetcher).toHaveBeenCalledWith('/api/worlds', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(asked),
  });
});

it('gives the drawn residents', async () => {
  const fetcher = vi.fn(async () => reply(200, { residents: ['a', 'b'] }));

  expect(await new ServerApi(fetcher).draw({ count: 2, picks: [], pins: [] })).toEqual(['a', 'b']);
  expect(fetcher.mock.calls[0]).toContain('/api/worlds/draw');
});

it('throws the server’s reason for a refusal', async () => {
  const fetcher = vi.fn(async () => reply(422, { error: 'No character x in the library' }));

  await expect(new ServerApi(fetcher).worlds()).rejects.toThrow('No character x in the library');
});

it('throws the status when there is no reason', async () => {
  const fetcher = vi.fn(async () => new Response('Bad gateway', { status: 502 }));

  await expect(new ServerApi(fetcher).characters()).rejects.toThrow('/api/characters: 502');
});
