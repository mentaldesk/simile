import { server, type Frame, type Wall } from '../net';

/** The latest `murals` and `paintings`, kept from startup since they come on connect. `version`
 * counts the changes, so the scene redraws only what changed. */
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

  /** The murals on a street. */
  muralsOn(street: string): Wall[] {
    return this.walls.filter((wall) => wall.map === street && wall.mural);
  }

  frame(map: string, id: string): Frame | undefined {
    return this.frames.find((frame) => frame.map === map && frame.id === id);
  }
}

export const sideWorks = new SideWorks();
