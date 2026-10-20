import Phaser from 'phaser';
import { MENU_SCENE } from '../menu';
import { SIDE_SCENE } from '../side';

/** `?harness=side` starts the side scene; the other harnesses set up their own world view. */
function devHarness(): string | undefined {
  if (!import.meta.env.DEV) return undefined;
  const params = new URLSearchParams(location.search);
  if (params.has('audio-harness')) return 'audio';
  return params.get('harness') ?? undefined;
}

export class BootScene extends Phaser.Scene {
  constructor() {
    super('boot');
  }

  create(): void {
    const harness = devHarness();
    if (harness === 'side') this.scene.start(SIDE_SCENE);
    else if (harness === undefined) this.scene.start(MENU_SCENE);
  }
}
