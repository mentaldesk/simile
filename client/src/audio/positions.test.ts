import { expect, it } from 'vitest';
import { positions, setPositionProvider } from './positions';

const provider = (x: number) => ({
  positionOf: (id: string) => (id === 'mei' ? { x, y: 0 } : undefined),
  listenerPosition: () => ({ x: 0, y: 0 }),
});

it('knows nothing until a provider is set', () => {
  expect(positions.positionOf('mei')).toBeUndefined();
  expect(positions.listenerPosition()).toBeUndefined();
});

it('asks the provider that is set now', () => {
  const remove = setPositionProvider(provider(1));

  expect(positions.positionOf('mei')).toEqual({ x: 1, y: 0 });
  expect(positions.listenerPosition()).toEqual({ x: 0, y: 0 });
  remove();
  expect(positions.positionOf('mei')).toBeUndefined();
});

it('keeps a newer provider when an older one is removed', () => {
  const removeOld = setPositionProvider(provider(1));
  const removeNew = setPositionProvider(provider(2));

  removeOld();

  expect(positions.positionOf('mei')).toEqual({ x: 2, y: 0 });
  removeNew();
});
