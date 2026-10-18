import { describe, expect, it } from 'vitest';
import type { GenerationEvent } from './api';
import { character } from './character.fixture';
import { Generation, passages } from './generation';

async function* events(...list: GenerationEvent[]): AsyncGenerator<GenerationEvent> {
  yield* list;
}

describe('a generation', () => {
  it('shows each call, thinking until its first words, then what it writes', async () => {
    let now = 0;
    const generation = new Generation(() => now);
    const statuses: string[] = [];
    generation.onChange = () => statuses.push(generation.status());
    const done = { type: 'done', character: character(), suggestions: [], notes: [], warnings: [] };
    const result = await generation.run(
      (async function* () {
        yield { type: 'call', purpose: 'character-biography' } as const;
        now = 51_000;
        yield { type: 'text', text: '{"backstory": "She fixes' } as const;
        yield { type: 'text', text: ' engines' } as const;
        yield { type: 'call', purpose: 'character-critic' } as const;
        now = 60_000;
        yield done as GenerationEvent;
      })(),
    );
    expect(result?.character.id).toBe('wren_abernethy');
    expect(statuses).toEqual([
      'Writing · thinking first, 0 s',
      'Writing · 51 s',
      'Writing · 51 s',
      'The critic is reading it · thinking first, 0 s',
      'Done in 60 s',
    ]);
    expect(generation.calls).toBe(2);
  });

  it('fails with the server’s error', async () => {
    const generation = new Generation();
    await generation.run(events({ type: 'error', error: 'usage limit reached' }));
    expect(generation.state).toBe('failed');
    expect(generation.status()).toBe('Failed: usage limit reached');
  });

  it('fails when the stream ends without a result', async () => {
    const generation = new Generation();
    await generation.run(events({ type: 'call', purpose: 'character-biography' }));
    expect(generation.error).toBe('The server stopped before it finished');
  });

  it('can be cancelled, which aborts its request', async () => {
    const generation = new Generation();
    const run = generation.run(
      (async function* () {
        yield { type: 'call', purpose: 'character-biography' } as const;
        await new Promise((_, reject) =>
          generation.signal.addEventListener('abort', () => reject(new Error('aborted'))),
        );
      })(),
    );
    await new Promise((resolve) => setTimeout(resolve, 0));
    expect(generation.state).toBe('thinking');
    generation.cancel();
    expect(await run).toBeNull();
    expect(generation.state).toBe('cancelled');
  });
});

describe('showing a reply as it’s written', () => {
  it('finds each string under its key, even cut off part-way', () => {
    const reply =
      '{"backstory": "She said \\"no\\".\\nThen", "interests": ["tides", "knots"], ' +
      '"voice": {"description": "Low", "reference_line": "The ferry eng';
    expect(passages(reply)).toEqual([
      { key: 'backstory', text: 'She said "no".\nThen' },
      { key: 'interests', text: 'tides' },
      { key: 'interests', text: 'knots' },
      { key: 'description', text: 'Low' },
      { key: 'reference_line', text: 'The ferry eng' },
    ]);
  });

  it('gives array items in objects the array’s key', () => {
    expect(passages('{"past": [{"x": 1}, "a"], "hooks": ["b"]}')).toEqual([
      { key: 'past', text: 'a' },
      { key: 'hooks', text: 'b' },
    ]);
  });

  it('drops a half-sent escape', () => {
    expect(passages('{"persona": "Blunt\\')).toEqual([{ key: 'persona', text: 'Blunt' }]);
  });
});
