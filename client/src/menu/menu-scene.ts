import Phaser from 'phaser';
import { ISO_SCENE } from '../scenes/iso-scene';
import { ServerApi } from './api';
import { Menu } from './menu';

export const MENU_SCENE = 'menu';

const hasCreator = Object.keys(import.meta.glob('../creator/index.ts')).length > 0;

export class MenuScene extends Phaser.Scene {
  constructor() {
    super(MENU_SCENE);
  }

  create(): void {
    if (new URLSearchParams(location.search).has('creator')) return;
    const menu = new Menu(document.body, new ServerApi(), {
      play: () => this.scene.start(ISO_SCENE),
      creator: hasCreator ? () => (location.search = '?creator') : undefined,
    });
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => menu.remove());
  }
}
