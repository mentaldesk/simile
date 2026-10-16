import type { ServerConnection } from '../net/connection';
import type { NpcState } from './state';

type Connection = Pick<ServerConnection, 'on' | 'send'>;

/** Whether the overlay is open and which NPC it shows, kept in step with the server. */
export class DebugWatch {
  open = false;
  npcId?: string;
  state?: Partial<NpcState>;
  readonly names = new Map<string, string>();
  onChange = () => {};
  private readonly connection: Connection;

  constructor(connection: Connection) {
    this.connection = connection;
    connection.on('snapshot', ({ entities }) => {
      this.names.clear();
      for (const { id, name } of entities) this.names.set(id, name);
      this.sendWatch();
    });
    connection.on('npc_state', ({ npc_id, state }) => {
      if (npc_id !== this.watching) return;
      this.state = state as Partial<NpcState>;
      this.onChange();
    });
  }

  /** The NPC the server should send state for: none while the overlay is closed. */
  get watching(): string | null {
    return this.open ? (this.npcId ?? null) : null;
  }

  toggle(): void {
    this.open = !this.open;
    this.changeTo(this.npcId);
  }

  select(npcId: string): void {
    if (this.open && npcId !== this.npcId) this.changeTo(npcId);
  }

  private changeTo(npcId: string | undefined): void {
    this.npcId = npcId;
    this.state = undefined;
    this.sendWatch();
    this.onChange();
  }

  private sendWatch(): void {
    this.connection.send({ type: 'watch_npc', npc_id: this.watching });
  }
}
