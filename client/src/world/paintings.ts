import { server, type Frame } from '../net';

type Server = Pick<typeof server, 'on'>;

/** The frames from the latest `paintings` message, kept from startup since it comes on connect. */
export class GalleryFrames {
  frames: Frame[] = [];
  private readonly listeners = new Set<(frames: Frame[]) => void>();

  constructor(server: Server) {
    server.on('paintings', ({ frames }) => {
      this.frames = frames;
      for (const listener of this.listeners) listener(frames);
    });
  }

  frame(map: string, id: string): Frame | undefined {
    return this.frames.find((frame) => frame.map === map && frame.id === id);
  }

  onChange(listener: (frames: Frame[]) => void): () => void {
    this.listeners.add(listener);
    return () => this.listeners.delete(listener);
  }
}

export const galleryFrames = new GalleryFrames(server);
