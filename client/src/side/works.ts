import { server, type Frame, type Wall } from '../net';

/** Kept from startup, since they come on connect. */
export class SideWorks {
  walls: Wall[] = [];
  frames: Frame[] = [];
  version = 0;

  constructor(on: Pick<typeof server, 'on'> = server) {
    on.on('murals', ({ walls }) => {
      this.walls = walls;
      this.version++;
    });
    on.on('paintings', ({ frames }) => {
      this.frames = frames;
      this.version++;
    });
  }
}

export const sideWorks = new SideWorks();
