export type HookKind =
  | 'estranged_sibling'
  | 'ex_partner'
  | 'old_friend'
  | 'rival'
  | 'debt'
  | 'secret'
  | 'betrayal'
  | 'saved_life';

export type Pin = { kind: HookKind; actor: string; target: string };

export type NewWorld = { count: number; picks: string[]; pins: Pin[] };

export type Resident = { id: string; name: string; age: number; occupation: string; home: string };

export type CurrentWorld = {
  name: string;
  default: boolean;
  data: string | null;
  residents: Resident[];
};

export type Worlds = { current: CurrentWorld; houses: number };

export type Bond = Pin & { pinned: boolean };

export type Missing = { id: string; name: string; needs: ('voice' | 'sprite')[] };

export type MadeWorld = {
  name: string;
  data: string;
  seed: number;
  residents: Resident[];
  bonds: Bond[];
  missing: Missing[];
  restart: { env: Record<string, string>; command: string };
};

export type LibraryCharacter = {
  id: string;
  name: string;
  birth_year: number;
  origin: string;
  occupation: string;
  persona: string;
  source: 'premade' | 'player';
};

export interface MenuApi {
  worlds(): Promise<Worlds>;
  characters(): Promise<LibraryCharacter[]>;
  draw(asked: NewWorld): Promise<string[]>;
  create(asked: NewWorld): Promise<MadeWorld>;
}

export class ServerApi implements MenuApi {
  private readonly fetcher: typeof fetch;

  constructor(fetcher: typeof fetch = (input, init) => fetch(input, init)) {
    this.fetcher = fetcher;
  }

  worlds(): Promise<Worlds> {
    return this.json('/api/worlds');
  }

  characters(): Promise<LibraryCharacter[]> {
    return this.json('/api/characters');
  }

  async draw(asked: NewWorld): Promise<string[]> {
    return (await this.json<{ residents: string[] }>('/api/worlds/draw', asked)).residents;
  }

  create(asked: NewWorld): Promise<MadeWorld> {
    return this.json('/api/worlds', asked);
  }

  private async json<T>(url: string, body?: unknown): Promise<T> {
    const init: RequestInit | undefined =
      body === undefined
        ? undefined
        : {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body),
          };
    const response = await this.fetcher(url, init);
    const data = await response.json().catch(() => null);
    if (!response.ok) throw new Error(data?.error ?? `${url}: ${response.status}`);
    return data as T;
  }
}
