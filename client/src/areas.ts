import type Phaser from 'phaser';

export type Area = { scenes?: Phaser.Types.Scenes.SceneType[] };

const sceneOrder = ['scenes', 'world', 'ui', 'debug'];

export function collectScenes(areas: Record<string, Area>): Phaser.Types.Scenes.SceneType[] {
  const rank = (path: string) => {
    const index = sceneOrder.indexOf(path.split('/')[1]);
    return index === -1 ? sceneOrder.length : index;
  };
  return Object.keys(areas)
    .sort((a, b) => rank(a) - rank(b) || a.localeCompare(b))
    .flatMap((path) => areas[path].scenes ?? []);
}
