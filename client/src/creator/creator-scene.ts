import Phaser from 'phaser';
import { ServerApi } from './api';
import { Creator } from './creator';

export const CREATOR_SCENE = 'creator';

export function wantsCreator(search: string = location.search): boolean {
  return new URLSearchParams(search).has('creator');
}

export class CreatorScene extends Phaser.Scene {
  constructor() {
    super({ key: CREATOR_SCENE, active: true });
  }

  create(): void {
    if (!wantsCreator()) return;
    const creator = new Creator(document.body, new ServerApi());
    this.events.once(Phaser.Scenes.Events.SHUTDOWN, () => creator.remove());
  }
}
