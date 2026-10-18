import { describe, expect, it, vi } from 'vitest';
import { ApiError, ServerApi, ndjson } from './api';
import { character } from './character.fixture';

function body(...chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream({
    start(controller) {
      chunks.forEach((chunk) => controller.enqueue(encoder.encode(chunk)));
      controller.close();
    },
  });
}

async function collect<T>(items: AsyncIterable<T>): Promise<T[]> {
  const found: T[] = [];
  for await (const item of items) found.push(item);
  return found;
}

describe('reading NDJSON', () => {
  it('yields each line, however the chunks split them', async () => {
    const lines = await collect(
      ndjson(body('{"type": "ca', 'll", "purpose": "x"}\n{"type"', ': "text", "text": "é"}\n')),
    );
    expect(lines).toEqual([
      { type: 'call', purpose: 'x' },
      { type: 'text', text: 'é' },
    ]);
  });

  it('cancels the response when the reader leaves early', async () => {
    const cancel = vi.fn();
    const stream = new ReadableStream<Uint8Array>({
      pull(controller) {
        controller.enqueue(new TextEncoder().encode('{"type": "text", "text": "a"}\n'));
      },
      cancel,
    });
    for await (const line of ndjson(stream)) {
      expect(line).toEqual({ type: 'text', text: 'a' });
      break;
    }
    expect(cancel).toHaveBeenCalled();
  });
});

describe('the server API', () => {
  it('streams a reroll of the sections asked for', async () => {
    const fetcher = vi.fn(async () => new Response(body('{"type": "error", "error": "no"}\n')));
    const api = new ServerApi(fetcher);
    const events = await collect(api.reroll(character(), ['voice']));
    expect(events).toEqual([{ type: 'error', error: 'no' }]);
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/characters/reroll');
    expect(JSON.parse(String(init.body))).toEqual({ character: character(), sections: ['voice'] });
  });

  it('turns a refusal into an error with the server’s reason', async () => {
    const fetcher = vi.fn(async () =>
      Response.json({ error: 'Premade characters are read-only' }, { status: 403 }),
    );
    const api = new ServerApi(fetcher);
    const error = await api.update(character()).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({ status: 403, message: 'Premade characters are read-only' });
  });

  it('sends a recording as the raw body', async () => {
    const fetcher = vi.fn(async () => Response.json({ id: 'job' }, { status: 202 }));
    const audio = new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/wav' });
    await new ServerApi(fetcher).record('wren_abernethy', audio);
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/characters/wren_abernethy/voice/recording');
    expect(init.body).toBe(audio);
    expect(init.headers).toEqual({ 'Content-Type': 'audio/wav' });
  });

  it.each([
    ['clip.m4a', 'audio/x-m4a', 'audio/mp4'],
    ['CLIP.MP3', '', 'audio/mpeg'],
    ['clip.wav', 'audio/x-wav', 'audio/wav'],
  ])('sends %s as the type the server takes, not %j', async (name, given, sent) => {
    const fetcher = vi.fn(async () => Response.json({ id: 'job' }, { status: 202 }));
    const file = new File([new Uint8Array([1, 2, 3])], name, { type: given });
    await new ServerApi(fetcher).record('wren_abernethy', file);
    const [, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(init.body).toBe(file);
    expect(init.headers).toEqual({ 'Content-Type': sent });
  });

  it('sends a character file as a zip, whatever the OS called it', async () => {
    const fetcher = vi.fn(async () => Response.json(character(), { status: 201 }));
    const file = new File(['PK'], 'wren.zip', { type: 'application/x-zip-compressed' });
    await new ServerApi(fetcher).importFile(file);
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe('/api/characters/import');
    expect(init.body).toBe(file);
    expect(init.headers).toEqual({ 'Content-Type': 'application/zip' });
  });

  it('sends what a clip says beside it', async () => {
    const fetcher = vi.fn(async () => Response.json({ id: 'job' }, { status: 202 }));
    const audio = new Blob([new Uint8Array([1, 2, 3])], { type: 'audio/mpeg' });
    await new ServerApi(fetcher).record('wren_abernethy', audio, 'Mind the step, it’s icy & wet.');
    const [url, init] = fetcher.mock.calls[0] as unknown as [string, RequestInit];
    const sent = new URL(url, 'http://localhost');
    expect(sent.pathname).toBe('/api/characters/wren_abernethy/voice/recording');
    expect(sent.searchParams.get('transcript')).toBe('Mind the step, it’s icy & wet.');
    expect(init.body).toBe(audio);
  });

  it('reads the player’s look', async () => {
    const appearance = character().appearance;
    const api = new ServerApi(vi.fn(async () => Response.json({ appearance })));
    expect(await api.player()).toEqual(appearance);
  });
});
