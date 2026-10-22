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
  | PaintingsMessage
  | PlayerStateMessage
  | JournalMessage
  | PlayerCollapsedMessage;
export type EntityKind = 'npc' | 'player';
/**
 * What someone is doing where they are. `climbing` is on stairs or a ladder, and `riding` in
 * a lift.
 */
export type Pose =
  'standing' | 'walking' | 'sitting' | 'reading' | 'working' | 'looking' | 'climbing' | 'riding';
/**
 * Which way someone faces on the map, x east and y south, by angle from east through south.
 * In side view, the three eastward values face right and the westward ones left, `north` shows
 * their back, looking into the picture, and `south` their front.
 */
export type Facing =
  'east' | 'south_east' | 'south' | 'south_west' | 'west' | 'north_west' | 'north' | 'north_east';
export type JsonValue = unknown;
/**
 * The way a wall faces. The iso camera sees only south and east faces, and a side-view map
 * has only south faces, towards the camera.
 */
export type Face = 'south' | 'east';
/**
 * What a carried thing is for: `salvage` to sell, `food` to eat, or the `lamp` to see by.
 */
export type ItemKind = 'salvage' | 'food' | 'lamp';
/**
 * A part fitted in place of one of the player's own. The hydraulic legs replace their legs,
 * the datajack takes a vertebra, and the one infrared eye takes either eye.
 */
export type Bionic = 'hydraulic_legs' | 'datajack' | 'infrared_eye';
/**
 * Where the player learned something: a `resident` told them, or they found a `clue`, such
 * as Aris's notes or a terminal.
 */
export type SourceKind = 'resident' | 'clue';
export type ClientMessage =
  | PlayerMoveMessage
  | PlayerSayMessage
  | WatchNpcMessage
  | ListNewsMessage
  | ReadNewsMessage
  | ListWorksMessage
  | ReadWorkMessage
  | EatMessage
  | PickUpMessage
  | SellMessage;

/**
 * The whole world, sent on connect. Replaces anything the client had.
 */
export interface SnapshotMessage {
  type: 'snapshot';
  /**
   * Sim time.
   */
  time: string;
  /**
   * The map the player starts on: the village, or a street on side-view maps.
   */
  map_id: string;
  entities: Entity[];
  /**
   * Only those still going on.
   */
  conversations: Conversation[];
}
/**
 * The server always sends `pose` and `facing`. Missing, they're standing, facing south-east.
 */
export interface Entity {
  id: string;
  kind: EntityKind;
  name: string;
  position: Position;
  pose?: Pose;
  facing?: Facing;
}
/**
 * Where an entity stands, in tiles: (4, 6) is on tile (4, 6). Fractions are mid-step. On a
 * side-view map, x runs along the street and y counts rows down from the top, and fractions are
 * mid-step or mid-climb, or for the player, mid-air in a jump or a fall.
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
/**
 * The server always sends `pose` and `facing`. Missing, they're standing, facing south-east.
 * On a side-view map, someone on stairs or a ladder is `climbing`. Taking stairs, a ladder or a
 * lift to another map is an `entity_moved` at its end, `climbing` or `riding`, held for the climb
 * or ride, then one onto the other map, as through a door.
 */
export interface EntityMovedMessage {
  type: 'entity_moved';
  entity_id: string;
  position: Position;
  pose?: Pose;
  facing?: Facing;
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
  /**
   * Whether the client shows a flush on the speaker: the line is a lie, as code decides it, and the player has the infrared eye. Left out unless true.
   */
  flushed?: boolean;
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
   * Three or four short paragraphs of plain text, separated by blank lines. Left out when there isn't one, so the client shows `summary`.
   */
  long_summary?: string | null;
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
 * Residents' writing at the terminals, newest first, and the notice board. The reply to
 * list_works and read_work.
 */
export interface WorksMessage {
  type: 'works';
  works: WrittenWork[];
  /**
   * The notices up on the board, newest first. Apart from the works.
   */
  notices: Notice[];
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
 * A short notice a shopkeeper, the `poster`, puts up at the terminals: an offer, an event or
 * an invitation. It isn't a work.
 */
export interface Notice {
  notice_id: string;
  title: string;
  /**
   * The notice itself, with its line breaks.
   */
  text: string;
  poster: Artist;
  /**
   * Sim time.
   */
  created: string;
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
   * The map it's on, such as a street. Left out on the village.
   */
  map?: string;
  /**
   * (x, y) is the building's tile at the west end of a south face or the north end of an east face: on its south row or east column, whatever storeys the mural spans. The face runs along that tile's south edge (y + 1) or east edge (x + 1). On a side-view map, it's the standing cell at the wall's west end, on the street in front of it.
   */
  x: number;
  /**
   * (x, y) is the building's tile at the west end of a south face or the north end of an east face: on its south row or east column, whatever storeys the mural spans. The face runs along that tile's south edge (y + 1) or east edge (x + 1). On a side-view map, it's the standing cell at the wall's west end, on the street in front of it.
   */
  y: number;
  /**
   * In tiles, east from (x, y) for a south face or south for an east face.
   */
  width: number;
  face: Face;
  /**
   * The mural's lower edge, in storeys above the ground there.
   */
  bottom: number;
  /**
   * The mural's upper edge, in storeys above the ground there.
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
   * The painting interactable's id.
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
/**
 * The player's money, what they carry, their body and their hunger, but never their humanity,
 * with the meal on offer and the buyer where they stand, and what's lying in the world for them
 * to pick up. Sent after the snapshot on connect, and whenever any of it changes.
 */
export interface PlayerStateMessage {
  type: 'player_state';
  player: Player;
  /**
   * The meal on offer where they stand: at home, or at a shop that's serving. Left out where there's none.
   */
  meal?: Meal | null;
  /**
   * Who buys where they stand, such as the scrap trader at their stall. Left out where there's none.
   */
  buyer?: Buyer | null;
  /**
   * What's lying in the world for them to pick up, on every map, besides what they left (`player.left`): salvage and secrets. Left out while there's none.
   */
  piles?: Pile[];
}
/**
 * The player's state, saved with the world. Each field defaults to the starting player's, so
 * a save from before the player loads with a whole body, no money and a charged lamp. Their
 * humanity is derived from the bionics fitted and isn't a field, so the client never sees it.
 */
export interface Player {
  /**
   * In the same units as the residents' money.
   */
  money: number;
  /**
   * What they carry. Picking things up keeps their weight within `carry_limit`.
   */
  items: Item[];
  /**
   * The most they carry, in kg.
   */
  carry_limit: number;
  body: Body;
  /**
   * 0 is fed and 1 is starving: they collapse.
   */
  hunger: number;
  /**
   * What they left lying in the world, oldest first: what they carried when they collapsed, on the tile they fell on or the ground below it, and anything of a pickup that didn't fit when they took from it. Left out while there's none.
   */
  left?: Pile[];
  /**
   * The pickups in the world they've taken from, by id, which stay taken. Left out while there's none.
   */
  taken?: string[];
}
/**
 * Something the player carries.
 */
export interface Item {
  /**
   * What it is, the same for every one of its kind, e.g. "copper_wire" or "lamp". Salvage is priced by it.
   */
  id: string;
  kind: ItemKind;
  /**
   * What the player sees, e.g. "Copper wire".
   */
  name: string;
  /**
   * In kg, counted against the carry limit.
   */
  weight: number;
  /**
   * A lamp's battery, from 0 (flat) to 1 (full). Null for anything else.
   */
  charge: number | null;
  /**
   * Whether a lamp is switched on, running its battery down. Null for anything else.
   */
  on: boolean | null;
}
/**
 * Each part of the player's body that can be sold or replaced: still `present`, `sold`, or
 * the bionic fitted in its place. A whole body has every part present.
 */
export interface Body {
  legs: ('present' | 'sold') | Bionic;
  vertebra: ('present' | 'sold') | Bionic;
  left_eye: ('present' | 'sold') | Bionic;
  right_eye: ('present' | 'sold') | Bionic;
  left_kidney: ('present' | 'sold') | Bionic;
  right_kidney: ('present' | 'sold') | Bionic;
}
/**
 * Items, money or both lying `at` a tile in the world for the player to pick up, such as
 * salvage, a secret's cash, or what they left when they collapsed.
 */
export interface Pile {
  at: MapTile;
  items: Item[];
  /**
   * Cash lying there, which weighs nothing. Left out while there's none.
   */
  money?: number;
}
/**
 * A tile on a given map: the village or an interior, or in side view a street or a floor.
 */
export interface MapTile {
  map: string;
  x: number;
  y: number;
}
/**
 * A meal the player can have where they stand, by sending `eat` without an item.
 */
export interface Meal {
  /**
   * Where: their home's location id, or a shop's.
   */
  place: string;
  /**
   * The place as the player sees it: "home", or a shop's name, e.g. "Golden Bowl Noodles".
   */
  name: string;
  /**
   * What it costs. Nothing at home.
   */
  price: number;
}
/**
 * Who buys things where the player stands, by sending `sell`: a stall, or a keeper at their
 * place.
 */
export interface Buyer {
  /**
   * Where: a location id, e.g. "scrap_stall" or "clinic".
   */
  place: string;
  /**
   * The buyer as the player sees it, e.g. "The scrap trader".
   */
  name: string;
  /**
   * What it pays for one of each thing they carry that it buys, by item `id`. Empty when they carry nothing it buys.
   */
  prices: {
    [k: string]: number;
  };
}
/**
 * What the player has learned about the incident, in the order they learned it, with the
 * leads still open. Sent after the snapshot on connect, and whenever an entry is added or a lead
 * is followed.
 */
export interface JournalMessage {
  type: 'journal';
  entries: JournalEntry[];
}
/**
 * Something the player learned about the incident: a fact, or a lie told about one.
 */
export interface JournalEntry {
  /**
   * The fact it's about. Several entries can be about one fact.
   */
  fact_id: string;
  /**
   * What they learned, as the journal puts it. A lie is written as it was told.
   */
  text: string;
  source: Source;
  /**
   * Sim time.
   */
  learned: string;
  /**
   * Whether the infrared eye saw the resident flush as they told it, which it shows exactly on a lie. Null if the player had no infrared eye then, and for a clue.
   */
  flushed: boolean | null;
  /**
   * The leads it opened that are still open: its fact's leads, and none for a lie. Each closes once any entry is about its fact, a lie included.
   */
  leads: Lead[];
}
/**
 * Who told them, or the clue they found it in.
 */
export interface Source {
  kind: SourceKind;
  /**
   * The resident's id, or the clue's interactable's.
   */
  id: string;
  /**
   * As the journal names them, e.g. "Kofi" or "Aris's notes".
   */
  name: string;
}
/**
 * Where the trail goes next: someone to ask or somewhere to look, which turns up a fact. It
 * closes once the journal has any entry about that fact, a lie included.
 */
export interface Lead {
  /**
   * The fact following it turns up.
   */
  fact_id: string;
  /**
   * For the journal, e.g. "Kofi paints in the lane at night. Ask him what he saw."
   */
  text: string;
}
/**
 * The player starved and collapsed. They wake at home, at `position`, still hungry, with
 * their lamp. Everything else they carried stays where they fell, in `player_state`'s `left`.
 */
export interface PlayerCollapsedMessage {
  type: 'player_collapsed';
  position: Position;
}
/**
 * A position without `map` is on the village. Side-view maps have no village, so there the
 * server ignores it, as it ignores any unknown map.
 *
 * On a side-view map the position can be mid-air, jumping or falling. The server keeps one in
 * open air over somewhere to land if it's within the farthest, highest jump the player can make
 * from somewhere to stand (a run jump with Space held, taking off as late as coyote time
 * allows), or if it's lower than the last position it kept on that map and within that jump's
 * reach of it along the row, as in a fall from any height. It ignores a position nobody could
 * be at.
 */
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
/**
 * The server ignores it if there's nothing to eat, or they can't pay.
 */
export interface EatMessage {
  type: 'eat';
  /**
   * A food item they carry, by its `id`, or null for the meal on offer where they stand, `player_state`'s `meal`.
   */
  item: string | null;
}
/**
 * Picks up, from the nearest pile within reach of the player, its money and each item that
 * still fits under their carry limit, in order. Any that don't fit stay in the pile.
 */
export interface PickUpMessage {
  type: 'pick_up';
}
/**
 * Sells to the buyer where the player stands, `player_state`'s `buyer`, for its price. The
 * server ignores it if there's no buyer, or they carry nothing it buys.
 */
export interface SellMessage {
  type: 'sell';
  /**
   * One thing they carry, by its `id`, or null for everything they carry that the buyer buys.
   */
  item: string | null;
}
