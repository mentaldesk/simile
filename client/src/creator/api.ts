import type { Appearance, Character, CharacterVoice, Gender, Values } from './character';
import type { Job, SocketLike } from './jobs';
import type { Latent } from './values';

export type Suggestion = { field: string; current: string; suggested: string };

export type Written = {
  character: Character;
  suggestions: Suggestion[];
  notes: string[];
  warnings: string[];
};

export type GenerationEvent =
  | { type: 'call'; purpose: string }
  | { type: 'text'; text: string }
  | ({ type: 'done' } & Written)
  | { type: 'error'; error: string };

export type Brief = {
  source: 'player';
  name?: string;
  birth_year?: number;
  gender?: Gender;
  origin?: string;
  arrival?: Character['arrival'];
  occupation?: string;
  values?: Values;
  latent?: Partial<Latent>;
  backstory?: string;
  persona?: string;
  speaking_style?: string;
  interests?: string[];
  past?: Character['past'];
  hooks?: Character['hooks'];
  appearance?: Appearance;
  voice?: CharacterVoice;
  craft?: Character['craft'];
};

export type Kind = { available: boolean; reason: string | null };
export type Capabilities = { machine: Record<string, boolean>; kinds: Record<string, Kind> };

export type LibraryVoice = {
  id: string;
  accent: string;
  age: 'young' | 'middle-aged' | 'older';
  gender: Gender;
  reference_line: string;
  clip: string;
};

export type Pick =
  { design: string; candidate: number } | { recording: string } | { library: string };

export type Atlas = {
  frames: Record<string, { frame: { x: number; y: number; w: number; h: number } }>;
};

export class ApiError extends Error {
  readonly status: number;

  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export interface CreatorApi {
  characters(): Promise<Character[]>;
  create(character: Character): Promise<Character>;
  update(character: Character): Promise<Character>;
  remove(id: string): Promise<void>;
  exportUrl(id: string): string;
  importFile(file: Blob): Promise<Character>;
  generate(brief: Brief, signal?: AbortSignal): AsyncIterable<GenerationEvent>;
  reroll(
    character: Character,
    sections: string[],
    signal?: AbortSignal,
  ): AsyncIterable<GenerationEvent>;
  player(): Promise<Appearance>;
  savePlayer(appearance: Appearance): Promise<Appearance>;
  capabilities(): Promise<Capabilities>;
  submit(kind: string, params: unknown): Promise<Job>;
  job(id: string): Promise<Job>;
  cancel(id: string): Promise<Job>;
  watch(id: string): SocketLike;
  atlas(url: string): Promise<Atlas | null>;
  voices(): Promise<LibraryVoice[]>;
  record(id: string, audio: Blob): Promise<Job>;
  pick(id: string, choice: Pick): Promise<Character>;
  say(id: string, line: string): Promise<Blob>;
}

type Fetch = typeof fetch;

export class ServerApi implements CreatorApi {
  private readonly fetcher: Fetch;
  private readonly socket: (url: string) => SocketLike;

  constructor(
    fetcher: Fetch = (input, init) => fetch(input, init),
    socket: (url: string) => SocketLike = (url) => new WebSocket(url) as unknown as SocketLike,
  ) {
    this.fetcher = fetcher;
    this.socket = socket;
  }

  characters(): Promise<Character[]> {
    return this.json('/api/characters');
  }

  create(character: Character): Promise<Character> {
    return this.json('/api/characters', 'POST', character);
  }

  update(character: Character): Promise<Character> {
    return this.json(`/api/characters/${character.id}`, 'PUT', character);
  }

  async remove(id: string): Promise<void> {
    await this.request(`/api/characters/${id}`, { method: 'DELETE' });
  }

  exportUrl(id: string): string {
    return `/api/characters/${id}/export`;
  }

  async importFile(file: Blob): Promise<Character> {
    const response = await this.request('/api/characters/import', { method: 'POST', body: file });
    return response.json();
  }

  generate(brief: Brief, signal?: AbortSignal): AsyncIterable<GenerationEvent> {
    return this.stream('/api/characters/generate', brief, signal);
  }

  reroll(
    character: Character,
    sections: string[],
    signal?: AbortSignal,
  ): AsyncIterable<GenerationEvent> {
    return this.stream('/api/characters/reroll', { character, sections }, signal);
  }

  async player(): Promise<Appearance> {
    return (await this.json<{ appearance: Appearance }>('/api/player')).appearance;
  }

  async savePlayer(appearance: Appearance): Promise<Appearance> {
    return (await this.json<{ appearance: Appearance }>('/api/player', 'PUT', { appearance }))
      .appearance;
  }

  capabilities(): Promise<Capabilities> {
    return this.json('/api/jobs/capabilities');
  }

  submit(kind: string, params: unknown): Promise<Job> {
    return this.json('/api/jobs', 'POST', { kind, params });
  }

  job(id: string): Promise<Job> {
    return this.json(`/api/jobs/${id}`);
  }

  cancel(id: string): Promise<Job> {
    return this.json(`/api/jobs/${id}/cancel`, 'POST');
  }

  watch(id: string): SocketLike {
    const scheme = location.protocol === 'https:' ? 'wss' : 'ws';
    return this.socket(`${scheme}://${location.host}/ws/jobs/${id}`);
  }

  async atlas(url: string): Promise<Atlas | null> {
    const response = await this.fetcher(url, { cache: 'no-cache' });
    return response.ok ? response.json() : null;
  }

  voices(): Promise<LibraryVoice[]> {
    return this.json('/api/voices');
  }

  async record(id: string, audio: Blob): Promise<Job> {
    const url = `/api/characters/${id}/voice/recording`;
    return (await this.request(url, { method: 'POST', body: audio })).json();
  }

  pick(id: string, choice: Pick): Promise<Character> {
    return this.json(`/api/characters/${id}/voice/pick`, 'POST', choice);
  }

  async say(id: string, line: string): Promise<Blob> {
    const init = { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify({ line }) };
    return (await this.request(`/api/characters/${id}/voice/try`, init)).blob();
  }

  private async *stream(url: string, body: unknown, signal?: AbortSignal) {
    const init = { method: 'POST', headers: JSON_HEADERS, body: JSON.stringify(body), signal };
    const response = await this.request(url, init);
    if (!response.body) throw new ApiError(response.status, 'The server sent nothing back');
    yield* ndjson<GenerationEvent>(response.body);
  }

  private async json<T>(url: string, method = 'GET', body?: unknown): Promise<T> {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = JSON_HEADERS;
      init.body = JSON.stringify(body);
    }
    return (await this.request(url, init)).json();
  }

  private async request(url: string, init: RequestInit): Promise<Response> {
    const response = await this.fetcher(url, init);
    if (response.ok) return response;
    const data = await response.json().catch(() => null);
    throw new ApiError(response.status, data?.error ?? `${url} answered ${response.status}`);
  }
}

const JSON_HEADERS = { 'Content-Type': 'application/json' };

export async function* ndjson<T>(body: ReadableStream<Uint8Array>): AsyncGenerator<T> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffered = '';
  let finished = false;
  try {
    while (!finished) {
      const { done, value } = await reader.read();
      finished = done;
      buffered += decoder.decode(value, { stream: !done });
      const lines = buffered.split('\n');
      buffered = done ? '' : (lines.pop() ?? '');
      for (const line of lines) if (line.trim()) yield JSON.parse(line) as T;
    }
  } finally {
    // Leaving early cancels the response, which stops the server's Claude call.
    if (!finished) await reader.cancel().catch(() => {});
    reader.releaseLock();
  }
}
