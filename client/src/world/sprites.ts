import type { Body, Facing } from './motion';

const SAMPLE_PREFIX = 'sample_';
const WALK_COLUMNS = [0, 1, 2, 1];
const STANDING_COLUMN = 1;

function fnv1a(text: string): number {
  let hash = 0x811c9dc5;
  for (let i = 0; i < text.length; i++) hash = Math.imul(hash ^ text.charCodeAt(i), 0x01000193);
  return hash >>> 0;
}

export function characterFor(entityId: string, available: readonly string[]): string {
  if (available.includes(entityId)) return entityId;
  const samples = available.filter((key) => key.startsWith(SAMPLE_PREFIX)).sort();
  return samples.length > 0 ? samples[fnv1a(entityId) % samples.length] : available[0];
}

export const walkAnimation = (character: string, facing: Facing) => `${character}-walk-${facing}`;

export const walkFrames = (facing: Facing) => WALK_COLUMNS.map((column) => `${facing}-${column}`);

export type Pose = { animation: string } | { frame: string };

export function poseOf(character: string, { facing, walking }: Body): Pose {
  return walking
    ? { animation: walkAnimation(character, facing) }
    : { frame: `${facing}-${STANDING_COLUMN}` };
}
