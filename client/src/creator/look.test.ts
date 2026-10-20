// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { DollManifest } from '../dolls/manifest';
import type { Capabilities, CreatorApi } from './api';
import { character } from './character.fixture';
import { type DrawPreview, type PreviewStage, SpritePreview, lookEditor } from './look';
import { PALETTE } from './palette';
import { PLAYER_ID, PlayerLookView } from './player-look';

const { flatDoll, shown } = vi.hoisted(() => ({ flatDoll: vi.fn(), shown: [] as unknown[] }));
vi.mock('../dolls/assets', () => ({ flatDoll }));
vi.mock('./doll-stage', () => ({
  DollStage: class {
    show = async (doll: unknown) => void shown.push(doll);
    destroy() {}
  },
}));

const LOOK = character().appearance;
const DOLL = { unit: 10, height: 20, flat: 'data:image/webp;base64,', pieces: {} } as unknown as DollManifest;
const CAN_DRAW: Capabilities = {
  machine: {},
  kinds: { sprite: { available: true, reason: null } },
};

function swatch(root: HTMLElement, row: string, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll('.creator-row')].find(
    (r) => r.querySelector('span')?.textContent === row,
  );
  return found!.querySelector<HTMLButtonElement>(`[aria-label="${name}"]`)!;
}

function fakeStage() {
  const stage = { show: vi.fn<PreviewStage['show']>(async () => {}), destroy: vi.fn() };
  return { stage, make: vi.fn(async () => stage) };
}

function editing(draw: DrawPreview, made = fakeStage()) {
  const sprite = new SpritePreview({} as CreatorApi, draw, 150, made.make);
  const root = lookEditor(LOOK, (look) => sprite.preview(look, 'wren_abernethy'));
  return { sprite, root, ...made };
}

describe('the live preview', () => {
  beforeEach(() => vi.useFakeTimers());

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
    flatDoll.mockReset();
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
    const { sprite, root, stage, make } = editing(draw);
    const dolls = sprite.root.querySelector<HTMLElement>('.creator-dolls')!;
    expect(dolls.hidden).toBe(true);

    sprite.preview(LOOK, 'wren_abernethy');
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
    const { sprite } = editing(draw);

    sprite.preview(LOOK);
    await vi.advanceTimersByTimeAsync(150);

    expect(sprite.root.textContent).toContain('Couldn’t draw the preview: busy');
  });

  it('asks for nothing after it’s disposed, and takes its stage down', async () => {
    const draw = vi.fn<DrawPreview>(async () => DOLL);
    const { sprite, root, stage } = editing(draw);
    sprite.preview(LOOK, 'wren_abernethy');
    await vi.advanceTimersByTimeAsync(150);

    swatch(root, 'Top', 'red').click();
    sprite.dispose();
    await vi.advanceTimersByTimeAsync(1000);

    expect(draw).toHaveBeenCalledOnce();
    expect(stage.destroy).toHaveBeenCalledOnce();
  });

  it('previews your look as it loads and as it changes, with the server’s flat doll', async () => {
    flatDoll.mockResolvedValue(DOLL);
    const api = { player: async () => LOOK, atlas: async () => null } as unknown as CreatorApi;
    const view = new PlayerLookView(api, CAN_DRAW, () => {});

    await vi.advanceTimersByTimeAsync(150);
    expect(flatDoll).toHaveBeenCalledExactlyOnceWith(LOOK, PLAYER_ID);
    expect(shown).toEqual([DOLL]);

    swatch(view.root, 'Shoes', 'red').click();
    await vi.advanceTimersByTimeAsync(150);
    expect(flatDoll).toHaveBeenLastCalledWith({ ...LOOK, shoe_colour: PALETTE.red }, PLAYER_ID);
    view.dispose();
  });
});
