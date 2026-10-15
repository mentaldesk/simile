import { describe, expect, it } from 'vitest';
import { collectScenes } from './areas';

class Boot {}
class World {}
class Hud {}
class Overlay {}
class Extra {}

describe('collectScenes', () => {
  it('orders scenes by area, unknown areas last', () => {
    const scenes = collectScenes({
      './debug/index.ts': { scenes: [Overlay] },
      './audio/index.ts': { scenes: [Extra] },
      './ui/index.ts': { scenes: [Hud] },
      './net/index.ts': {},
      './world/index.ts': { scenes: [World] },
      './scenes/index.ts': { scenes: [Boot] },
    });

    expect(scenes).toEqual([Boot, World, Hud, Overlay, Extra]);
  });
});
