import { describe, expect, it } from 'vitest';
import { collectScenes } from './areas';

class World {}
class Hud {}
class Overlay {}
class Extra {}

describe('collectScenes', () => {
  it('orders scenes by area, unknown areas last', () => {
    const scenes = collectScenes({
      './debug/index.ts': { scenes: [Overlay] },
      './zzz/index.ts': { scenes: [Extra] },
      './ui/index.ts': { scenes: [Hud] },
      './net/index.ts': {},
      './world/index.ts': { scenes: [World] },
    });

    expect(scenes).toEqual([World, Hud, Overlay, Extra]);
  });
});
