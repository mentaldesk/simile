// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DollManifest } from '../dolls/manifest';
import type { Capabilities, CreatorApi } from './api';
import { character } from './character.fixture';
import type { Job, SocketLike } from './jobs';
import { DollPreview, type DrawPreview, type PreviewStage, lookEditor } from './look';
import { PALETTE } from './palette';
import { PLAYER_ID, PlayerLookView } from './player-look';

const { flatDoll, loadDoll, shown } = vi.hoisted(() => ({
  flatDoll: vi.fn(),
  loadDoll: vi.fn(),
  shown: [] as unknown[],
}));
vi.mock('../dolls/assets', () => ({ flatDoll, loadDoll }));
vi.mock('./doll-stage', () => ({
  DollStage: class {
    show = async (doll: unknown) => void shown.push(doll);
    destroy() {}
  },
}));

const LOOK = character().appearance;
const DOLL = { unit: 10, height: 20, flat: 'data:image/webp;base64,', pieces: {} } as unknown as DollManifest;
const CAN_PAINT: Capabilities = {
  machine: {},
  kinds: { doll: { available: true, reason: null } },
};

function swatch(root: HTMLElement, row: string, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll('.creator-row')].find(
    (r) => r.querySelector('span')?.textContent === row,
  );
  return found!.querySelector<HTMLButtonElement>(`[aria-label="${name}"]`)!;
}

function buttonCalled(root: HTMLElement, text: string): HTMLButtonElement {
  return [...root.querySelectorAll('button')].find((b) => b.textContent === text)!;
}

function fakeStage() {
  const stage = { show: vi.fn<PreviewStage['show']>(async () => {}), destroy: vi.fn() };
  return { stage, make: vi.fn(async () => stage) };
}

function editing(draw: DrawPreview, made = fakeStage()) {
  const preview = new DollPreview({} as CreatorApi, draw, 150, made.make);
  const root = lookEditor(LOOK, (look) => preview.preview(look, 'wren_abernethy'));
  return { preview, root, ...made };
}

describe('the live preview', () => {
  beforeEach(() => vi.useFakeTimers());

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    flatDoll.mockReset();
    loadDoll.mockReset();
    shown.length = 0;
  });

  it('redraws once the controls have been still for the delay', async () => {
    const draw = vi.fn<DrawPreview>(async () => DOLL);
    const { root } = editing(draw);

    swatch(root, 'Top', 'red').click();
    await vi.advanceTimersByTimeAsync(100);
    swatch(root, 'Top', 'blue').click();
    await vi.advanceTimersByTimeAsync(149);
    expect(draw).not.toHaveBeenCalled();
    await vi.advanceTimersByTimeAsync(1);

    expect(draw).toHaveBeenCalledOnce();
    expect(draw).toHaveBeenCalledWith({
      character: 'wren_abernethy',
      appearance: { ...LOOK, top_colour: PALETTE.blue },
    });
  });

  it('never has more than one request in flight, and catches up with the last change', async () => {
    let inFlight = 0;
    let most = 0;
    const finish: (() => void)[] = [];
    const draw = vi.fn<DrawPreview>(() => {
      most = Math.max(most, ++inFlight);
      return new Promise((resolve) =>
        finish.push(() => {
          inFlight -= 1;
          resolve(DOLL);
        }),
      );
    });
    const { root } = editing(draw);

    swatch(root, 'Top', 'red').click();
    await vi.advanceTimersByTimeAsync(150);
    swatch(root, 'Top', 'blue').click();
    await vi.advanceTimersByTimeAsync(150);
    swatch(root, 'Top', 'lime').click();
    await vi.advanceTimersByTimeAsync(1000);
    expect(draw).toHaveBeenCalledOnce();

    finish[0]();
    await vi.advanceTimersByTimeAsync(0);
    expect(draw).toHaveBeenCalledTimes(2);
    expect(draw.mock.calls[1][0].appearance.top_colour).toBe(PALETTE.lime);

    finish[1]();
    await vi.advanceTimersByTimeAsync(1000);
    expect(draw).toHaveBeenCalledTimes(2);
    expect(most).toBe(1);
  });

  it('shows the look’s flat doll on a stage it makes once', async () => {
    const other = { ...DOLL, height: 21 };
    const draw = vi.fn<DrawPreview>(async ({ appearance }) => (appearance === LOOK ? DOLL : other));
    const { preview, root, stage, make } = editing(draw);
    const dolls = preview.root.querySelector<HTMLElement>('.creator-dolls')!;
    expect(dolls.hidden).toBe(true);

    preview.preview(LOOK, 'wren_abernethy');
    await vi.advanceTimersByTimeAsync(150);
    expect(make).toHaveBeenCalledWith(dolls);
    expect(stage.show).toHaveBeenLastCalledWith(DOLL);
    expect(dolls.hidden).toBe(false);

    swatch(root, 'Top', 'red').click();
    await vi.advanceTimersByTimeAsync(150);
    expect(stage.show).toHaveBeenLastCalledWith(other);
    expect(make).toHaveBeenCalledOnce();
  });

  it('says why a preview failed', async () => {
    const draw = vi.fn<DrawPreview>(async () => Promise.reject(new Error('busy')));
    const { preview } = editing(draw);

    preview.preview(LOOK);
    await vi.advanceTimersByTimeAsync(150);

    expect(preview.root.textContent).toContain('Couldn’t draw the preview: busy');
  });

  it('asks for nothing after it’s disposed, and takes its stage down', async () => {
    const draw = vi.fn<DrawPreview>(async () => DOLL);
    const { preview, root, stage } = editing(draw);
    preview.preview(LOOK, 'wren_abernethy');
    await vi.advanceTimersByTimeAsync(150);

    swatch(root, 'Top', 'red').click();
    preview.dispose();
    await vi.advanceTimersByTimeAsync(1000);

    expect(draw).toHaveBeenCalledOnce();
    expect(stage.destroy).toHaveBeenCalledOnce();
  });

  it('previews your look as it loads and as it changes, with the server’s flat doll', async () => {
    flatDoll.mockResolvedValue(DOLL);
    const api = { player: async () => LOOK } as unknown as CreatorApi;
    const view = new PlayerLookView(api, null, () => {});

    await vi.advanceTimersByTimeAsync(150);
    expect(flatDoll).toHaveBeenCalledExactlyOnceWith(LOOK, PLAYER_ID);
    expect(shown).toEqual([DOLL]);

    swatch(view.root, 'Shoes', 'red').click();
    await vi.advanceTimersByTimeAsync(150);
    expect(flatDoll).toHaveBeenLastCalledWith({ ...LOOK, shoe_colour: PALETTE.red }, PLAYER_ID);
    view.dispose();
  });
});

const SOCKET: SocketLike = { onmessage: null, onclose: null, close: () => {} };

function job(overrides: Partial<Job>): Job {
  return {
    id: 'a1b2c3d4e5f60718',
    kind: 'doll',
    state: 'succeeded',
    progress: 1,
    message: 'Painted',
    error: null,
    result: { doll: '/api/jobs/files/doll/player.json' },
    created: '2026-10-21T09:30:00Z',
    started: '2026-10-21T09:30:00Z',
    finished: '2026-10-21T09:31:00Z',
    ...overrides,
  };
}

function jobsApi(done: Job) {
  return {
    player: vi.fn(async () => LOOK),
    savePlayer: vi.fn(async (look) => look),
    submit: vi.fn(async () => done),
    job: vi.fn(async () => done),
    watch: vi.fn(() => SOCKET),
  };
}

describe('painting the doll', () => {
  const PAINTED = {
    ...DOLL,
    appearance: LOOK,
    flat: '/api/jobs/files/doll/player-flat.webp',
    painted: '/p.webp',
  };

  beforeEach(() => vi.useFakeTimers());

  afterEach(() => {
    vi.useRealTimers();
    flatDoll.mockReset();
    loadDoll.mockReset();
    shown.length = 0;
  });

  it('saves your look and paints it with the doll job, then shows the painted doll', async () => {
    flatDoll.mockResolvedValue(DOLL);
    loadDoll.mockImplementation(async (url: string) =>
      url === '/api/jobs/files/doll/player.json' ? PAINTED : Promise.reject(new Error('404')),
    );
    const api = jobsApi(job({}));
    const view = new PlayerLookView(api as unknown as CreatorApi, CAN_PAINT, () => {});
    await vi.advanceTimersByTimeAsync(150);
    expect(shown).toEqual([PAINTED]);
    shown.length = 0;

    swatch(view.root, 'Shoes', 'red').click();
    await vi.advanceTimersByTimeAsync(150);
    expect(shown).toEqual([DOLL]);
    buttonCalled(view.root, 'Save').click();
    await vi.advanceTimersByTimeAsync(150);

    const look = { ...LOOK, shoe_colour: PALETTE.red };
    expect(api.savePlayer).toHaveBeenCalledWith(look);
    expect(api.submit).toHaveBeenCalledExactlyOnceWith('doll', {
      character: PLAYER_ID,
      appearance: look,
    });
    expect(shown.at(-1)).toEqual({
      ...PAINTED,
      flat: '/api/jobs/files/doll/player-flat.webp?job=a1b2c3d4e5f60718',
      painted: '/p.webp?job=a1b2c3d4e5f60718',
    });
    expect(view.root.textContent).toContain('Doll painted.');
    view.dispose();
  });

  it('keeps the flat doll and says why where the doll job fails', async () => {
    flatDoll.mockResolvedValue(DOLL);
    loadDoll.mockRejectedValue(new Error('404'));
    const failed = job({ state: 'failed', error: 'Painting dolls needs FLUX', result: null });
    const api = jobsApi(failed);
    const view = new PlayerLookView(api as unknown as CreatorApi, CAN_PAINT, () => {});
    await vi.advanceTimersByTimeAsync(150);
    expect(view.root.textContent).toContain('This look isn’t painted yet: saving paints it.');

    swatch(view.root, 'Shoes', 'red').click();
    buttonCalled(view.root, 'Save').click();
    await vi.advanceTimersByTimeAsync(150);

    expect(api.submit).toHaveBeenCalledOnce();
    expect(shown.at(-1)).toBe(DOLL);
    expect(view.root.textContent).toContain('Doll: Failed: Painting dolls needs FLUX');
    view.dispose();
  });

  it('keeps the flat doll where the painted one is of another look', async () => {
    flatDoll.mockResolvedValue(DOLL);
    loadDoll.mockResolvedValue({ ...PAINTED, appearance: { ...LOOK, shoe_colour: PALETTE.red } });
    const view = new PlayerLookView(jobsApi(job({})) as unknown as CreatorApi, CAN_PAINT, () => {});
    await vi.advanceTimersByTimeAsync(150);

    expect(shown).toEqual([DOLL]);
    expect(view.root.textContent).toContain('This look isn’t painted yet: saving paints it.');
    view.dispose();
  });

  it('only previews the flat doll where the server can’t paint one', async () => {
    flatDoll.mockResolvedValue(DOLL);
    const api = jobsApi(job({}));
    const view = new PlayerLookView(api as unknown as CreatorApi, null, () => {});
    await vi.advanceTimersByTimeAsync(150);

    swatch(view.root, 'Shoes', 'red').click();
    buttonCalled(view.root, 'Save').click();
    await vi.advanceTimersByTimeAsync(150);

    expect(api.savePlayer).toHaveBeenCalled();
    expect(api.submit).not.toHaveBeenCalled();
    expect(loadDoll).not.toHaveBeenCalled();
    expect(shown).toEqual([DOLL, DOLL]);
    view.dispose();
  });
});
