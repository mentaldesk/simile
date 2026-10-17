const SAMPLE_PREFIX = 'sample_';

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
