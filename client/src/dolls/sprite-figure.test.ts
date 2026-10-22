import { describe, expect, it, vi } from 'vitest';
import { dolls } from './assets';
import { drawnImage, fakeScene, loadingImages } from './phaser.fixture';
import { shown } from './sprite';
import { SpriteFigure } from './sprite-figure';

vi.mock('phaser', () => import('./phaser.fixture'));

const atlases = Object.keys(dolls).map((id) => `figure-${id}`);

describe('wearing another figure', () => {
  it('draws it the same size, in the pose it was in, once its atlas has loaded', async () => {
    const figure = new SpriteFigure(fakeScene(atlases), 0, 0, dolls.player, 'figure-player', 245);
    figure.setPose('walking', 'west', 0.3);

    await figure.wear(dolls.player_legs);

    expect(figure.figure).toBe(dolls.player_legs);
    const image = drawnImage(figure);
    expect(image.key).toBe('figure-player_legs');
    expect(image.frame).toBe(shown(dolls.player_legs, 'walking', 'west', 0.3).frame);
    expect(image.flipX).toBe(true);
    expect((figure as unknown as { scale: number }).scale).toBeCloseTo(245 / dolls.player_legs.height);
  });

  it('wears the last of several asked for while their atlases load, whichever loads last', async () => {
    const loads = loadingImages();
    const figure = new SpriteFigure(fakeScene(['figure-player']), 0, 0, dolls.player, 'figure-player');

    const legs = figure.wear(dolls.player_legs);
    const eye = figure.wear(dolls.player_eye);
    loads[1].onload();
    await eye;
    loads[0].onload();
    await legs;

    expect(figure.figure).toBe(dolls.player_eye);
    expect(drawnImage(figure).key).toBe('figure-player_eye');
  });

  it('keeps its figure if it was destroyed while the atlas loaded', async () => {
    const loads = loadingImages();
    const scene = fakeScene(['figure-player']);
    const figure = new SpriteFigure(scene, 0, 0, dolls.player, 'figure-player');

    const legs = figure.wear(dolls.player_legs);
    figure.destroy();
    loads[0].onload();
    await legs;

    expect(figure.figure).toBe(dolls.player);
  });
});
