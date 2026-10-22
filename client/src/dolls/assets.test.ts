import { describe, expect, it, vi } from 'vitest';
import { dolls, flatDoll, loadDoll } from './assets';
import { isFigure } from './manifest';

const figure = {
  ppm: 80,
  height: 163.2,
  painted: 'new_face.webp',
  frames: { stand: { frame: [0, 0, 60, 170], feet: [30, 168] } },
  poses: { stand: ['stand'], walk: ['stand'], run: ['stand'], sit: ['stand'], climb: ['stand'] },
};

describe('the committed figures', () => {
  it('load for every resident, the doctor and the player, each with its atlas', () => {
    expect(Object.keys(dolls).sort()).toEqual([
      'annelie',
      'desmond',
      'henrietta',
      'ingrid',
      'kofi',
      'lachlan',
      'marguerite',
      'mirela',
      'odalys',
      'player',
      'player_datajack',
      'player_datajack_eye',
      'player_eye',
      'player_legs',
      'player_legs_datajack',
      'player_legs_datajack_eye',
      'player_legs_eye',
      'priya',
      'raymond',
      'tobias',
    ]);
    for (const [id, doll] of Object.entries(dolls)) {
      expect(doll.id).toBe(id);
      expect(isFigure(doll)).toBe(true);
      expect(doll.painted).toMatch(new RegExp(`${id}\\.webp$`));
      expect(doll.ppm).toBe(80);
      expect(Object.keys(doll.frames).length).toBeGreaterThanOrEqual(5);
    }
  });

  it('say which is no villager’s: the doctor’s', () => {
    expect(Object.keys(dolls).filter((id) => dolls[id]!.resident === false)).toEqual(['annelie']);
  });
});

describe('flatDoll', () => {
  it('asks the server for any look', async () => {
    const flat = { unit: 5, height: 100, flat: 'data:image/webp;base64,AA', pieces: {} };
    const fetcher = vi.fn(async () => Response.json(flat));

    const found = await flatDoll({ skin: '#733e39' }, 'new_face', fetcher);

    expect(fetcher).toHaveBeenCalledWith('/api/dolls/flat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ appearance: { skin: '#733e39' }, character: 'new_face' }),
    });
    expect(found.flat).toBe('data:image/webp;base64,AA');
    expect(isFigure(found)).toBe(false);
  });

  it('fails when the server refuses', async () => {
    const fetcher = vi.fn(async () => new Response('{}', { status: 422 }));

    await expect(flatDoll({}, undefined, fetcher)).rejects.toThrow('422');
  });
});

describe('loadDoll', () => {
  it("resolves a painted figure's atlas against its manifest", async () => {
    const fetcher = vi.fn(async () => Response.json(figure));

    const found = await loadDoll('http://localhost/api/jobs/files/doll/new_face.json', fetcher);

    expect(found.painted).toBe('http://localhost/api/jobs/files/doll/new_face.webp');
    expect(isFigure(found)).toBe(true);
  });

  it('refuses a paper doll painted before figures, so the look is painted again', async () => {
    const old = { unit: 5, height: 100, flat: 'old-flat.webp', painted: 'old-painted.webp', pieces: {} };
    const fetcher = vi.fn(async () => Response.json(old));

    await expect(loadDoll('http://localhost/api/jobs/files/doll/old.json', fetcher)).rejects.toThrow('paper doll');
  });
});
