// Generated from server/simile/protocol/protocol.schema.json by protocol.test.ts.
// Don't edit it by hand: docs/protocol.md says how to regenerate it.

export type Message = ServerMessage | ClientMessage;
export type ServerMessage =
  | SnapshotMessage
  | ClockMessage
  | EntityMovedMessage
  | ConversationStartedMessage
  | ConversationEndedMessage
  | LineMessage
  | NpcStateMessage
  | NewsMessage
  | WorksMessage
  | MuralsMessage
  | PaintingsMessage;
export type EntityKind = 'npc' | 'player';
export type JsonValue = unknown;
/**
 * The way a wall faces. The iso camera sees only south and east faces.
 */
export type Face = 'south' | 'east';
export type ClientMessage =
  | PlayerMoveMessage
  | PlayerSayMessage
  | WatchNpcMessage
  | ListNewsMessage
  | ReadNewsMessage
  | ListWorksMessage
  | ReadWorkMessage;

/**
 * The whole world, sent on connect. Replaces anything the client had.
 */
export interface SnapshotMessage {
  type: 'snapshot';
  /**
   * Sim time.
   */
  time: string;
  map_id: string;
  entities: Entity[];
  /**
   * Only those still going on.
   */
  conversations: Conversation[];
}
export interface Entity {
  id: string;
  kind: EntityKind;
  name: string;
  position: Position;
}
/**
 * Where an entity stands, in tiles: (4, 6) is on tile (4, 6). Fractions are mid-step.
 */
export interface Position {
  x: number;
  y: number;
  /**
   * The map it's on. The server always sends it, and a client that leaves it out means the village.
   */
  map?: string;
}
export interface Conversation {
  id: string;
  /**
   * @minItems 2
   */
  participants: [string, string, ...string[]];
  started: string;
  /**
   * Null while it's going on.
   */
  ended: string | null;
  lines: Line[];
}
export interface Line {
  /**
   * Unique across the world. Audio for the line carries it.
   */
  id: number;
  conversation_id: string;
  speaker: string;
  text: string;
  /**
   * When the speaker starts saying it.
   */
  timestamp: string;
  /**
   * Estimated seconds to say it aloud.
   */
  duration: number;
}
/**
 * The sim clock, sent after the snapshot, when the speed changes and every sim minute.
 */
export interface ClockMessage {
  type: 'clock';
  /**
   * Sim time.
   */
  time: string;
  /**
   * Sim seconds per real second.
   */
  speed: number;
}
export interface EntityMovedMessage {
  type: 'entity_moved';
  entity_id: string;
  position: Position;
}
export interface ConversationStartedMessage {
  type: 'conversation_started';
  conversation: Conversation;
}
export interface ConversationEndedMessage {
  type: 'conversation_ended';
  conversation_id: string;
  ended: string;
}
export interface LineMessage {
  type: 'line';
  line: Line;
  /**
   * Whether audio_chunk frames will follow for this line.
   */
  voiced: boolean;
}
/**
 * Debug state for the overlay. The fields in `state` are up to the modules that send them.
 */
export interface NpcStateMessage {
  type: 'npc_state';
  npc_id: string;
  state: {
    [k: string]: JsonValue;
  };
}
/**
 * The articles at the news terminals, newest first. The reply to list_news and read_news.
 */
export interface NewsMessage {
  type: 'news';
  articles: NewsArticle[];
}
export interface NewsArticle {
  news_id: string;
  title: string;
  /**
   * The feed it came from, e.g. "The Atlantic". May be empty.
   */
  source: string;
  /**
   * Plain text.
   */
  summary: string;
  /**
   * The original article.
   */
  url: string;
  /**
   * Whether the player has read it.
   */
  read: boolean;
}
/**
 * Residents' writing at the terminals, newest first. The reply to list_works and read_work.
 */
export interface WorksMessage {
  type: 'works';
  works: WrittenWork[];
}
export interface WrittenWork {
  work_id: string;
  title: string;
  artist: Artist;
  /**
   * What the artist makes, e.g. "short poems about the river".
   */
  form: string;
  /**
   * The piece itself, with its line breaks.
   */
  text: string;
  /**
   * The artist on what it's saying.
   */
  statement: string;
  /**
   * Sim time.
   */
  created: string;
  /**
   * Whether the player has read it.
   */
  read: boolean;
}
export interface Artist {
  id: string;
  name: string;
}
/**
 * Every mural wall and what's on it. Sent on connect and whenever a mural changes.
 */
export interface MuralsMessage {
  type: 'murals';
  walls: Wall[];
}
export interface Wall {
  id: string;
  /**
   * (x, y) is the building's tile at the west end of a south face or the north end of an east face: on its south row or east column, whatever storeys the mural spans. The face runs along that tile's south edge (y + 1) or east edge (x + 1).
   */
  x: number;
  /**
   * (x, y) is the building's tile at the west end of a south face or the north end of an east face: on its south row or east column, whatever storeys the mural spans. The face runs along that tile's south edge (y + 1) or east edge (x + 1).
   */
  y: number;
  /**
   * In tiles, east from (x, y) for a south face or south for an east face.
   */
  width: number;
  face: Face;
  /**
   * The mural's lower edge, in storeys above the ground.
   */
  bottom: number;
  /**
   * The mural's upper edge, in storeys above the ground.
   */
  top: number;
  /**
   * Null while the wall is blank.
   */
  mural: Mural | null;
}
export interface Mural {
  work_id: string;
  title: string;
  artist: Artist;
  /**
   * The artist on what it's saying.
   */
  statement: string;
  /**
   * The URL of the mural's image, /api/works/<work_id>.png.
   */
  image: string;
}
/**
 * Every frame and the painting in it. Sent on connect and whenever a painting changes.
 */
export interface PaintingsMessage {
  type: 'paintings';
  frames: Frame[];
}
export interface Frame {
  /**
   * The painting interactable's id, which is also its frame's id in the interior's iso manifest.
   */
  id: string;
  /**
   * The map the interactable is on.
   */
  map: string;
  /**
   * Null while the frame is empty.
   */
  painting: Painting | null;
}
export interface Painting {
  work_id: string;
  title: string;
  artist: Artist;
  /**
   * The artist on what it's saying.
   */
  statement: string;
  /**
   * The URL of the painting's image. Each work has its own.
   */
  image: string;
}
export interface PlayerMoveMessage {
  type: 'player_move';
  position: Position;
}
export interface PlayerSayMessage {
  type: 'player_say';
  text: string;
  /**
   * The NPC the player is talking to.
   */
  target: string;
}
export interface WatchNpcMessage {
  type: 'watch_npc';
  /**
   * The NPC to send npc_state for, or null to stop.
   */
  npc_id: string | null;
}
export interface ListNewsMessage {
  type: 'list_news';
}
export interface ReadNewsMessage {
  type: 'read_news';
  /**
   * The article the player reads.
   */
  news_id: string;
}
export interface ListWorksMessage {
  type: 'list_works';
}
export interface ReadWorkMessage {
  type: 'read_work';
  /**
   * The work the player reads.
   */
  work_id: string;
}
