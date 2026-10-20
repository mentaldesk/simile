import { describe, expect, it, vi } from 'vitest';
import { flatDoll, loadDoll } from './assets';

const doll = {
  unit: 5,
  height: 100,
  flat: 'new_face-flat.webp',
  painted: 'new_face-painted.webp',
  pieces: {},
};

describe('flatDoll', () => {
  it('asks the server for any look', async () => {
    const fetcher = vi.fn(async () =>
      Response.json({ ...doll, flat: 'data:image/webp;base64,AA', painted: undefined }),
    );

    const found = await flatDoll({ skin: '#733e39' }, 'new_face', fetcher);

    expect(fetcher).toHaveBeenCalledWith('/api/dolls/flat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ appearance: { skin: '#733e39' }, character: 'new_face' }),
    });
    expect(found.flat).toBe('data:image/webp;base64,AA');
  });

  it('fails when the server refuses', async () => {
    const fetcher = vi.fn(async () => new Response('{}', { status: 422 }));

    await expect(flatDoll({}, undefined, fetcher)).rejects.toThrow('422');
  });
});

describe('loadDoll', () => {
  it("resolves a published doll's atlases against its manifest", async () => {
    const fetcher = vi.fn(async () => Response.json(doll));

    const found = await loadDoll('http://localhost/api/jobs/files/doll/new_face.json', fetcher);

    expect(found.flat).toBe('http://localhost/api/jobs/files/doll/new_face-flat.webp');
    expect(found.painted).toBe('http://localhost/api/jobs/files/doll/new_face-painted.webp');
  });
});
