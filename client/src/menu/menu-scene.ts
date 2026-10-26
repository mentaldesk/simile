import Phaser from 'phaser';
import { SIDE_SCENE } from '../side';
import { ServerApi } from './api';
import { Menu } from './menu';

export const MENU_SCENE = 'menu';

const hasCreator = Object.keys(import.meta.glob('../creator/index.ts')).length > 0;

export class MenuScene extends Phaser.Scene {
  constructor() {
    super(MENU_SCENE);
  }

  create(): void {
    const params = new URLSearchParams(location.search);
    if (params.has('play')) {
      this.scene.start(SIDE_SCENE);
      return;
    }
    if (params.has('creator')) return;
    const menu = new Menu(document.body, new ServerApi(), {
      play: () => this.scene.start(SIDE_SCENE),
      enter: () => location.assign(`${location.pathname}?play`),
      creator: hasCreator ? () => (location.search = '?creator') : undefined,
    });
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => menu.remove());
  }
}
