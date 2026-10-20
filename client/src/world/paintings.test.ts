import { describe, expect, it } from 'vitest';
import { server, type Frame } from '../net';
import { GalleryFrames } from './paintings';

const hung = (id: string, workId: string, map = 'gallery_floor_0'): Frame => ({
  id,
  map,
  painting: {
    work_id: workId,
    title: `Title of ${workId}`,
    artist: { id: 'kofi', name: 'Kofi Mensah' },
    statement: 'About it.',
    image: `/api/gallery/${workId}.png`,
  },
});

describe('GalleryFrames', () => {
  it('keeps the latest frames from the server and says when they change', () => {
    const frames = new GalleryFrames(server);
    const heard: Frame[][] = [];
    const stop = frames.onChange((changed) => heard.push(changed));

    server.dispatch(JSON.stringify({ type: 'paintings', frames: [hung('painting_1', 'a')] }));

    expect(frames.frame('gallery_floor_0', 'painting_1')?.painting?.work_id).toBe('a');
    expect(frames.frame('gallery_floor_1', 'painting_1')).toBeUndefined();
    expect(heard).toHaveLength(1);
    stop();
    server.dispatch(JSON.stringify({ type: 'paintings', frames: [] }));
    expect(heard).toHaveLength(1);
  });
});
