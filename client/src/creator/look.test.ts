// @vitest-environment jsdom
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { WALK_FPS } from '../world/tuning';
import type { Capabilities, CreatorApi } from './api';
import { character } from './character.fixture';
import { type DrawPreview, SpritePreview, drawPreview, lookEditor } from './look';
import { PALETTE } from './palette';
import { PLAYER_ID, PlayerLookView } from './player-look';

const LOOK = character().appearance;
const PNG = new Blob([], { type: 'image/png' });
const CAN_DRAW: Capabilities = {
  machine: {},
  kinds: { sprite: { available: true, reason: null } },
};

const fakeContext = () => ({ imageSmoothingEnabled: true, scale: vi.fn(), drawImage: vi.fn() });

function swatch(root: HTMLElement, row: string, name: string): HTMLButtonElement {
  const found = [...root.querySelectorAll('.creator-row')].find(
    (r) => r.querySelector('span')?.textContent === row,
  );
  return found!.querySelector<HTMLButtonElement>(`[aria-label="${name}"]`)!;
}

function editing(draw: DrawPreview) {
  const sprite = new SpritePreview({} as CreatorApi, draw, 150);
  const root = lookEditor(LOOK, (look) => sprite.preview(look, 'wren_abernethy'));
  return { sprite, root };
}

describe('the live sprite preview', () => {
  let context: ReturnType<typeof fakeContext>;

  beforeEach(() => {
    vi.useFakeTimers();
    context = fakeContext();
    vi.stubGlobal('createImageBitmap', async () => ({ width: 48, height: 96 }));
    vi.spyOn(HTMLCanvasElement.prototype, 'getContext').mockReturnValue(context as never);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('redraws once the controls have been still for the delay', async () => {
    const draw = vi.fn<DrawPreview>(async () => PNG);
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
          resolve(PNG);
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

  it('walks the four three-quarter directions side by side at the game’s 4×', async () => {
    const { sprite } = editing(async () => PNG);
    sprite.preview(LOOK, 'wren_abernethy');
    await vi.advanceTimersByTimeAsync(150);
    const canvas = sprite.root.querySelector('canvas')!;
    const lastFour = () =>
      context.drawImage.mock.calls.slice(-4).map(([, sx, sy, , , dx]) => [sx, sy, dx]);

    expect(canvas.hidden).toBe(false);
    expect([canvas.width, canvas.height]).toEqual([(4 * 16 + 3 * 4) * 4, 24 * 4]);
    expect(context.scale).toHaveBeenLastCalledWith(4, 4);
    expect(lastFour()).toEqual([
      [0, 0, 0],
      [0, 24, 20],
      [0, 48, 40],
      [0, 72, 60],
    ]);
    const columns = [];
    for (let step = 0; step < 4; step++) {
      await vi.advanceTimersByTimeAsync(1000 / WALK_FPS);
      columns.push(lastFour().map(([sx]) => sx));
    }
    expect(columns).toEqual([
      [16, 16, 16, 16],
      [32, 32, 32, 32],
      [16, 16, 16, 16],
      [0, 0, 0, 0],
    ]);
  });

  it('says why a preview failed', async () => {
    const draw = vi.fn<DrawPreview>(async () => Promise.reject(new Error('busy')));
    const { sprite } = editing(draw);

    sprite.preview(LOOK);
    await vi.advanceTimersByTimeAsync(150);

    expect(sprite.root.textContent).toContain('Couldn’t draw the preview: busy');
  });

  it('asks for nothing after it’s disposed', async () => {
    const draw = vi.fn<DrawPreview>(async () => PNG);
    const { sprite, root } = editing(draw);

    swatch(root, 'Top', 'red').click();
    sprite.dispose();
    await vi.advanceTimersByTimeAsync(1000);

    expect(draw).not.toHaveBeenCalled();
  });

  it('previews your look as it loads and as it changes', async () => {
    const fetch = vi.fn<typeof globalThis.fetch>(async () => new Response(PNG));
    vi.stubGlobal('fetch', fetch);
    const api = { player: async () => LOOK, atlas: async () => null } as unknown as CreatorApi;
    const view = new PlayerLookView(api, CAN_DRAW, () => {});
    const sent = (call: number) => JSON.parse(String(fetch.mock.calls[call][1]?.body));

    await vi.advanceTimersByTimeAsync(150);
    expect(fetch).toHaveBeenCalledOnce();
    expect(fetch.mock.calls[0][0]).toBe('/api/art/preview');
    expect(sent(0)).toEqual({ character: PLAYER_ID, appearance: LOOK });

    swatch(view.root, 'Shoes', 'red').click();
    await vi.advanceTimersByTimeAsync(150);
    expect(fetch).toHaveBeenCalledTimes(2);
    expect(sent(1)).toEqual({
      character: PLAYER_ID,
      appearance: { ...LOOK, shoe_colour: PALETTE.red },
    });
    view.dispose();
  });

  it('passes on what the server refused', async () => {
    const refusal = Response.json({ error: 'appearance.skin: not a colour' }, { status: 422 });
    vi.stubGlobal('fetch', async () => refusal);

    await expect(drawPreview({ appearance: LOOK })).rejects.toThrow('not a colour');
  });
});
