/** The `state` of an `npc_state` message, as `server/simile/debug/` builds it. */
export type NpcState = {
  name: string;
  occupation: string;
  time: string;
  goal: string;
  walking: boolean;
  paused: boolean;
  since: string;
  until: string | null;
  needs: Record<string, number>;
  options: Record<string, number>;
  reasons: Record<string, Reason>;
  intentions: IntentionRow[];
  values: Record<string, number>;
  relationships: RelationshipRow[];
  memories: MemoryRow[];
  conversation: ConversationState | null;
};

/** Something they said they'd do. `following` is null until it's due. */
export type IntentionRow = {
  kind: string;
  target: string | null;
  description: string;
  promised_to: string[];
  due: string;
  expires: string;
  following?: boolean | null;
};

/** Why an option scored higher: the intention that raised it, and by how much. */
export type Reason = IntentionRow & { bonus: number };

export type RelationshipRow = {
  about: string;
  like: number;
  trust: number;
  respect: number;
  familiarity: number;
  flags: { kind: string; description: string; open: boolean }[];
};

export type MemoryRow = {
  kind: string;
  content: string;
  timestamp: string;
  salience: number;
  valence: number;
};

export type ConversationState = {
  id: string;
  talking_to: string;
  engagement: number;
  leaving: boolean;
  lines: { speaker: string; text: string; timestamp: string }[];
};
