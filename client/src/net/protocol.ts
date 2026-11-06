// Generated from server/simile/protocol/protocol.schema.json by protocol.test.ts.
// Don't edit it by hand: docs/protocol.md says how to regenerate it.

export type Message = ServerMessage | ClientMessage;
export type ServerMessage =
  | SnapshotMessage
  | ClockMessage
  | EntityMovedMessage
  | CreatureMovedMessage
  | CreatureGoneMessage
  | CreatureHitMessage
  | MachineChangedMessage
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
  | PlayerDiedMessage;
export type EntityKind = 'npc' | 'player';
/**
 * What someone is doing where they are. `climbing` is on stairs or a ladder, `riding` in a
 * lift, and `sleeping` lying asleep in a bed, on a bed spot's cell.
 */
export type Pose =
  | 'standing'
  | 'walking'
  | 'sitting'
  | 'reading'
  | 'working'
  | 'looking'
  | 'climbing'
  | 'riding'
  | 'sleeping';
/**
 * Which way someone faces on the map, x east and y south, by angle from east through south.
 * In side view, the three eastward values face right and the westward ones left, `north` shows
 * their back, looking into the picture, and `south` their front.
 */
export type Facing =
  'east' | 'south_east' | 'south' | 'south_west' | 'west' | 'north_west' | 'north' | 'north_east';
/**
 * What a creature is, named as its figure is in `content/creatures/`: a `rat`, a recycler
 * `bot`, a wild `dog` or a `bat`.
 */
export type CreatureKind = 'rat' | 'bot' | 'dog' | 'bat';
/**
 * Which way something faces or acts on a side-view map, where only right and left draw:
 * `east`, to the right, or `west`, to the left.
 */
export type SideFacing = 'east' | 'west';
/**
 * What a creature is doing, which picks the pose its figure plays. `idle` stands, or for a
 * bat flies on the spot. `moving`, `chasing` and `fleeing` play its kind's cycle: walk, run or
 * fly. `attacking` plays its attack, and `roosting`, a bat's alone, hangs from the ceiling.
 * `hurt` stands, or for a bat flies.
 */
export type CreatureState =
  'idle' | 'moving' | 'chasing' | 'fleeing' | 'attacking' | 'roosting' | 'hurt';
/**
 * What a machine in the maker space is: Aris's 3D `printer`, or the `recycler`.
 */
export type MachineKind = 'printer' | 'recycler';
/**
 * Whether it needs repairing first.
 */
export type MachineState = 'broken' | 'working';
/**
 * What it's for: `salvage` to sell, `food` to eat, the `lamp` to see by, a `part` to fit,
 * `material` to print with, a `weapon` to fire, `rounds` to load it with, or a salvaged `bionic`
 * to have refitted.
 */
export type ItemKind =
  'salvage' | 'food' | 'lamp' | 'part' | 'material' | 'weapon' | 'rounds' | 'bionic';
/**
 * What the printer prints with, which decides how hard its weapons and rounds hit.
 */
export type Material = 'plastic';
/**
 * A part fitted in place of the player's own: a grade of the power cell, the legs or the
 * feet, the datajack or the eye.
 */
export type Bionic =
  | 'datajack'
  | 'infrared_eye'
  | 'power_cell'
  | 'power_cell_2'
  | 'power_cell_3'
  | 'bionic_legs'
  | 'bionic_legs_2'
  | 'bionic_legs_3'
  | 'spring_feet'
  | 'spring_feet_2';
export type JsonValue = unknown;
/**
 * The way a wall faces. The iso camera sees only south and east faces, and a side-view map
 * has only south faces, towards the camera.
 */
export type Face = 'south' | 'east';
/**
 * An ailment and its cause: a `rat_bite`, the `infection` an untreated bite can turn into, or
 * a dose of `radiation`.
 */
export type EffectKind = 'rat_bite' | 'infection' | 'radiation';
export type BodyPart =
  | 'legs'
  | 'vertebra'
  | 'left_eye'
  | 'right_eye'
  | 'left_kidney'
  | 'right_kidney'
  | 'stomach'
  | 'feet';
/**
 * Why a shop that sells meals isn't serving them: `closed`, not serving now, off shift or past
 * last orders, or `sold_out`, open but with nothing left of its batch for this shift.
 */
export type ShutReason = 'closed' | 'sold_out';
/**
 * Where the player learned something: a `resident` told them, or they found a `clue`, such
 * as Aris's notes or a terminal.
 */
export type SourceKind = 'resident' | 'clue';
/**
 * What runs out when the player dies.
 */
export type Vital = 'hunger' | 'power' | 'health';
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
  | SellMessage
  | LampMessage
  | SellPartMessage
  | FitMessage
  | SellRecipeMessage
  | BuyMessage
  | TreatMessage
  | RestMessage
  | FireMessage
  | ReloadMessage
  | RepairMessage
  | MakeMessage
  | StashMessage;

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
  /**
   * Which of the generated levels in content/street/levels/ this world plays, picked by its seed: the maps in `levels/<level>/`, such as the sewers.
   */
  level?: number;
  /**
   * Every creature on every map. The server always sends it, and missing, there are none.
   */
  creatures?: Creature[];
  /**
   * Every machine you repair and then use. The server always sends it, and missing, there are none.
   */
  machines?: Machine[];
}
/**
 * The server always sends `pose` and `facing`. Missing, they're standing, facing south-east.
 * A resident asleep in their bed is `sleeping`, on the bed spot's cell.
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
 * A danger in the tunnels, ticked by the sim, which the client draws and animates. A walking
 * kind's `position` is the ground under it, and a bat's the middle of it, in the air, or for one
 * roosting the ceiling it hangs from. Creatures are only on side-view maps, so each faces right
 * or left.
 */
export interface Creature {
  id: string;
  kind: CreatureKind;
  position: Position;
  facing: SideFacing;
  state: CreatureState;
  /**
   * How much it has left, from 1, unhurt, to 0, when it's gone. Left out while it's full.
   */
  health?: number;
}
/**
 * The state of a machine you repair and then use. Where it stands and what it's called are
 * on the map, in the `Interactable` with the same `id`.
 */
export interface Machine {
  /**
   * Its interactable's id, e.g. "printer_3d".
   */
  id: string;
  kind: MachineKind;
  state: MachineState;
  /**
   * What repairing it uses up while it's broken, how many of each by item `id`, e.g. `{"copper_wire": 2}`. Empty once it works.
   */
  parts: {
    [k: string]: number;
  };
  /**
   * What it can make while it works, whether or not they have what it takes, each item once. Empty while it's broken, and it can be empty while it works.
   */
  makes: Product[];
}
/**
 * Something a working machine makes: the `item` that comes out, stack and all, such as 6
 * rounds, and what it takes.
 */
export interface Product {
  item: Item;
  /**
   * What it's made from: a material they carry, or scrap, by weight.
   */
  uses: Material | 'scrap';
  /**
   * How much of it: a material's amount, or kilos of scrap.
   */
  cost: number;
}
/**
 * Something the player carries, or a stack of it.
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
   * In kg, each, counted against the carry limit.
   */
  weight: number;
  /**
   * How many in the stack. Only material and rounds stack: rounds come whole, and material in any amount, since it comes from scrap by weight. Left out while it's 1.
   */
  amount?: number;
  /**
   * A lamp's battery, from 0 (flat) to 1 (full). It runs down while the lamp is on, and at a plug it charges, on or off. Null for anything else.
   */
  charge: number | null;
  /**
   * Whether a lamp is switched on, running its battery down. The player switches it, and it goes off by itself when it's flat. Null for anything else.
   */
  on: boolean | null;
  /**
   * What material, rounds or a weapon are made of. A material's `id` is this. Left out for anything else.
   */
  material?: Material | null;
  /**
   * The rounds loaded in a weapon, up to its `capacity`. Left out for anything else.
   */
  rounds?: number | null;
  /**
   * The most rounds a weapon holds. Left out for anything else.
   */
  capacity?: number | null;
  /**
   * A weapon's wear, from 1 (new) to 0 (worn out). Left out for anything else.
   */
  condition?: number | null;
  /**
   * What a salvaged bionic refits as, grade and all, which is also its `id`. Left out for anything else.
   */
  bionic?: Bionic | null;
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
 * or ride, then one onto the other map, as through a door. Going to bed is an `entity_moved` onto
 * the bed spot's cell, `sleeping`, held until they wake and the next one gets them up.
 */
export interface EntityMovedMessage {
  type: 'entity_moved';
  entity_id: string;
  position: Position;
  pose?: Pose;
  facing?: Facing;
}
/**
 * A creature moved, turned, changed state or lost health, or appeared: one the client doesn't
 * have yet is new. On its way somewhere, it's sent as it goes.
 */
export interface CreatureMovedMessage {
  type: 'creature_moved';
  creature: Creature;
}
/**
 * A creature is gone from the world, such as a rat the player jumps on.
 */
export interface CreatureGoneMessage {
  type: 'creature_gone';
  creature_id: string;
}
/**
 * A creature was hurt, for the client to draw. A `creature_moved` with its `health` or a
 * `creature_gone` follows, so the client still has it.
 */
export interface CreatureHitMessage {
  type: 'creature_hit';
  creature_id: string;
}
/**
 * A machine changed, such as one just repaired: all of it, to replace what the client has.
 */
export interface MachineChangedMessage {
  type: 'machine_changed';
  machine: Machine;
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
 * The player's money, what they carry, their body, their vitals and what they know, but never
 * their humanity, with the recipes they know, the meal on offer or the shop that's shut and the
 * buyer where they stand, and what's lying in the world for them to pick up. Sent after the
 * snapshot on connect, and whenever any of it changes.
 */
export interface PlayerStateMessage {
  type: 'player_state';
  player: Player;
  /**
   * Each recipe in `player.mind`, in full and in the same order. Left out while they know none.
   */
  recipes?: Recipe[];
  /**
   * The meal on offer where they stand: at home, or at a shop that's serving. Left out where there's none.
   */
  meal?: Meal | null;
  /**
   * The shop where they stand, if it sells meals but isn't serving them, and why. Left out everywhere else.
   */
  shut?: Shut | null;
  /**
   * Who buys where they stand, such as the scrap trader at their stall. Left out where there's none.
   */
  buyer?: Buyer | null;
  /**
   * What's lying in the world for them to pick up, on every map, besides what they left (`player.left`): salvage and secrets. Left out while there's none.
   */
  piles?: Pile[];
  /**
   * The cell of their own bed at home where they stand, where `rest` lies them down. Left out everywhere else.
   */
  bed?: MapTile | null;
  /**
   * Whether they're resting in that bed, from `rest` until they're fully healed, move off it or get up. Left out unless they are.
   */
  resting?: boolean;
}
/**
 * The player's state, saved with the world. Each field defaults to the starting player's, so
 * a save from before the player loads with a whole body, no money, a charged lamp, nothing known,
 * full health, no effects, nothing searched, an empty stash, no corpses and nothing repaired. A
 * save holding the old 10 kg carry limit loads with 15. Their humanity is derived from the bionics
 * fitted and isn't a field, so the client never sees it.
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
  stash?: Stash;
  body: Body;
  mind?: Mind;
  /**
   * 0 is fed and 1 is starving, which hurts until they eat.
   */
  hunger: number;
  /**
   * Their power cell's charge, from 1 (full) to 0 (flat: they die), which they run on in place of hunger once a cell is in their stomach. It stays full without one. Left out while it's full.
   */
  power?: number;
  /**
   * From 1, unhurt, to 0, when they die. Left out while it's full.
   */
  health?: number;
  /**
   * Their ailments, in the order they got them, each kind once. Left out while there's none.
   */
  effects?: Effect[];
  /**
   * What they left lying in the world, oldest first: what they carried when they collapsed, on the tile they fell on or the ground below it, a destroyed bot's haul, on the cell it went down in, and anything of a pickup that didn't fit when they took from it. Left out while there's none.
   */
  left?: Pile[];
  /**
   * Their own bodies, oldest first, each where they died. Left out while there's none.
   */
  corpses?: Corpse[];
  /**
   * When each pickup in the world was last emptied, by the player or a recycler bot, in sim time, by pickup id. Salvage lies there again a while after it was taken, but a secret, cash or a ration, stays taken for good. Left out while there's none.
   */
  taken?: {
    [k: string]: string;
  };
  /**
   * What they've sold that its buyer keeps for them to buy back, oldest first. Left out while there's none.
   */
  sales?: Sale[];
  /**
   * The searchable things and jacks they've searched, by interactable id, in the order they searched them. Each is searched once, and holds nothing after. Left out while there's none.
   */
  searched?: string[];
  /**
   * The machines they've repaired, by interactable id, in the order they repaired them, saved here and shown by the snapshot and `machine_changed`. Left out while there's none.
   */
  repaired?: string[];
}
/**
 * What they keep at home. Left out while it's empty and at its starting limit.
 */
export interface Stash {
  /**
   * What's in it. Putting things in keeps their weight within `limit`.
   */
  items: Item[];
  /**
   * The most it holds, in kg.
   */
  limit: number;
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
  /**
   * Left out while it's still theirs, as in a save from before it could go.
   */
  stomach?: ('present' | 'sold') | Bionic;
  /**
   * Left out while they're still theirs, as in a save from before they could go.
   */
  feet?: ('present' | 'sold') | Bionic;
}
/**
 * What the player knows, which they keep when they die. Left out of `Player` while they know
 * no recipe.
 */
export interface Mind {
  /**
   * The recipes they know, by the bionic each builds, in the order they learned them.
   */
  recipes: Bionic[];
  /**
   * The recipes they've sold to the clinic, in the order they sold them. They still know each, and can't sell it again. Left out while there's none.
   */
  sold?: Bionic[];
}
/**
 * An ailment the player has, which fades on its own or lasts until it's treated.
 */
export interface Effect {
  kind: EffectKind;
  /**
   * How bad it is, up to 1. It's gone once it fades to 0.
   */
  strength: number;
  /**
   * The strength it loses each sim hour, or null while it lasts until it's treated, at the clinic or with medicine.
   */
  fades: number | null;
  /**
   * When they got it, in sim time.
   */
  since: string;
}
/**
 * Items, money or both lying `at` a tile in the world for the player to pick up, such as
 * salvage, a secret's cash, a destroyed bot's haul, or what they left when they collapsed.
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
 * A body left `at` the tile it fell on, or the ground below it, with what was on it. It can
 * hold nothing at all: it stays whatever it holds, unlike a `Pile`.
 */
export interface Corpse {
  /**
   * Which corpse, as two can lie on one tile.
   */
  id: string;
  /**
   * Whose body it was: `"player"` for the player's own.
   */
  owner: string;
  at: MapTile;
  /**
   * The cash still on it.
   */
  money: number;
  /**
   * What it still carries.
   */
  items: Item[];
  /**
   * The bionics still in it, which come out as `bionic` items.
   */
  bionics: Bionic[];
}
/**
 * Something the player sold that its buyer keeps for them to buy back.
 */
export interface Sale {
  item: Item;
  /**
   * The buyer that has it, by its place, e.g. "scrap_stall".
   */
  place: string;
  /**
   * What it fetched.
   */
  price: number;
}
/**
 * How to build a `bionic`, which the clinic needs before it fits one. It's known by the
 * bionic it builds.
 */
export interface Recipe {
  bionic: Bionic;
  /**
   * The bionic as the player sees it, e.g. "Datajack".
   */
  name: string;
  /**
   * The items the fitting uses up, how many of each by item `id`, e.g. `{"copper_wire": 3, "usb_c_connector": 1}`.
   */
  parts: {
    [k: string]: number;
  };
  /**
   * What the fitting costs, from their money.
   */
  credits: number;
  /**
   * The parts of their body it can go in place of, any one of which they give up for it, or a lower grade of its line fitted there: the bionic's own, filled in from it when left out.
   */
  replaces: BodyPart[];
  /**
   * What must be fitted first, each of them or a higher grade of its line: a power cell for everything but a cell.
   */
  after: Bionic[];
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
 * A shop where the player stands that sells meals but isn't serving them now.
 */
export interface Shut {
  /**
   * The shop's location id, e.g. "noodle_bar".
   */
  place: string;
  /**
   * The shop as the player sees it, e.g. "Golden Bowl Noodles".
   */
  name: string;
  reason: ShutReason;
  /**
   * When it next starts serving: the next start of a shift of whoever works there, after now, even while they're due but haven't come. Null when nobody works there or they have no shifts.
   */
  opens: string | null;
}
/**
 * Who trades where the player stands: buys with `sell` and `sell_part`, fits with `fit`,
 * treats with `treat`, and sells with `buy`.
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
  /**
   * What it pays for each part of their body it would buy now, by `sell_part`, by `Body` field, e.g. `{"left_kidney": 100}`. The clinic's doctor buys one kidney, never the second. Left out while it would buy none.
   */
  parts?: {
    [k: string]: number;
  };
  /**
   * Every bionic it fits that they know the recipe for and haven't fitted, by `fit`, whether or not they can pay, each once, with why when it can't fit it yet. Left out while there are none.
   */
  fittings?: Fitting[];
  /**
   * What it pays, once, for each recipe they know that it would buy now, by `sell_recipe`, by the bionic it builds. Left out while it would buy none.
   */
  recipes?: {
    [k: string]: number;
  };
  /**
   * What it sells now, by `buy`, whether or not they can pay, such as what they sold it, to buy back. Left out while there's nothing.
   */
  stock?: Offer[];
  /**
   * What it would treat now, by `treat`, whether or not they can pay, each once: patching them up while they're hurt, and each effect they have that it treats. Left out while there's nothing.
   */
  treatments?: Treatment[];
}
/**
 * A bionic the buyer fits, by `fit`, for its `price` and one of the player's `parts`, unless
 * it's `blocked`.
 */
export interface Fitting {
  bionic: Bionic;
  /**
   * The bionic as the player sees it, e.g. "Spring feet".
   */
  name: string;
  price: number;
  /**
   * The parts of their body it can go in place of, any one of which they give up for it: `["legs"]`, or `["left_eye", "right_eye"]` for an eye.
   *
   * @minItems 1
   */
  parts: [BodyPart, ...BodyPart[]];
  /**
   * Why the buyer can't fit it yet, as the player reads it, such as "Needs a power cell first." or "Out of stock.", while it refuses to `fit` it. Left out while it would fit it now.
   */
  blocked?: string | null;
}
/**
 * Something a buyer sells, by `buy`, for its `price`.
 */
export interface Offer {
  item: Item;
  price: number;
}
/**
 * Something the buyer treats, by `treat`, for its `price`: patching up their health, or an
 * effect they have.
 */
export interface Treatment {
  /**
   * The effect it treats, or null for patching up their health to full.
   */
  effect: EffectKind | null;
  /**
   * The treatment as the player sees it, e.g. "Patch up".
   */
  name: string;
  price: number;
}
/**
 * What the player has learned about Aris's disappearance, in the order they learned it, with
 * the leads still open. Sent after the snapshot on connect, and whenever an entry is added or a
 * lead is followed.
 */
export interface JournalMessage {
  type: 'journal';
  entries: JournalEntry[];
}
/**
 * Something the player learned about Aris's disappearance: a fact, or a lie told about one.
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
   * For the journal, e.g. "Kofi saw her the evening before she went missing. Ask him where she was going."
   */
  text: string;
}
/**
 * The player died of `cause`: they starved, their power cell ran flat, or they had no health
 * left. They wake at `position`, in their bed or at the entry of `home` if it has no bed, in a
 * whole organic body. Their corpse stays where they fell, or where they wake if the server didn't
 * know where that was, at the end of `player_state`'s `corpses`.
 */
export interface PlayerDiedMessage {
  type: 'player_died';
  position: Position;
  cause: Vital;
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
 * still fits under their carry limit, in order. Any that don't fit stay in the pile. A nearer
 * clue is found instead, and so is a clue in the jack they stand at, with the datajack.
 *
 * A searchable thing they stand at that they haven't searched is searched before anything else:
 * they learn the recipe it teaches and take what it holds, as from a pile, and what doesn't fit
 * is left where they stand. So is a jack that holds or teaches anything, with the datajack, and
 * its clue is found on the next one.
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
   * One thing they carry, by its `id`, or null for everything they carry that the buyer buys except the lamp, which is only sold on its own.
   */
  item: string | null;
}
/**
 * Switches the lamp the player carries on or off. The server ignores it if they carry no
 * lamp, and for switching on a flat one.
 */
export interface LampMessage {
  type: 'lamp';
  on: boolean;
}
/**
 * Sells a part of their body to the buyer where they stand, at its `buyer.parts` price.
 */
export interface SellPartMessage {
  type: 'sell_part';
  part: BodyPart;
}
/**
 * Has the buyer where they stand fit a bionic in place of `part`, for its `fittings` price.
 */
export interface FitMessage {
  type: 'fit';
  bionic: Bionic;
  part: BodyPart;
}
/**
 * Sells a recipe they know, by the bionic it builds, to the buyer where they stand, at its
 * `buyer.recipes` price. They still know it, and can't sell it again.
 */
export interface SellRecipeMessage {
  type: 'sell_recipe';
  recipe: Bionic;
}
/**
 * Buys one of something the buyer where they stand sells, `player_state`'s `buyer`'s
 * `stock`, at its price.
 */
export interface BuyMessage {
  type: 'buy';
  /**
   * What they buy, by its `id`: the first of that id in `stock`.
   */
  item: string;
}
/**
 * Has the buyer where they stand give a treatment, for its `treatments` price.
 */
export interface TreatMessage {
  type: 'treat';
  /**
   * The effect to treat, or null for patching up their health.
   */
  effect: EffectKind | null;
}
/**
 * Lies the player down in their bed where they stand, `player_state`'s `bed`, or gets them up.
 * The server ignores it away from their bed, at full health, while they're infected, and when
 * they're already resting or up as asked.
 */
export interface RestMessage {
  type: 'rest';
  on: boolean;
}
/**
 * Fires the first weapon they carry that's loaded and not worn out, the way they face, along
 * the row from where the server last kept them. The server doesn't track the player's facing, so
 * the client says it. The server ignores it if they carry no such weapon.
 */
export interface FireMessage {
  type: 'fire';
  facing: SideFacing;
}
/**
 * Loads the first weapon they carry that has room and isn't worn out, with as many as fit of
 * the rounds they carry of its `material`. The server ignores it if there's no such weapon, or
 * they carry no such rounds.
 */
export interface ReloadMessage {
  type: 'reload';
}
/**
 * Repairs the broken machine they stand at, using up its `parts`. The server ignores it if
 * they aren't at it, it isn't broken, or they don't carry every part.
 */
export interface RepairMessage {
  type: 'repair';
  /**
   * The machine, by its `id`.
   */
  machine: string;
}
/**
 * Has the working machine they stand at make one of its `makes`, using up what it takes. A
 * product that uses scrap takes all the scrap they carry, at that rate: their `salvage` items,
 * except those a recipe or a machine's repair uses. The server ignores it if they aren't at it,
 * it doesn't make that, they don't have what it takes, or what they'd end up carrying wouldn't
 * fit under their carry limit.
 */
export interface MakeMessage {
  type: 'make';
  /**
   * The machine, by its `id`.
   */
  machine: string;
  /**
   * What they make, by the `id` of its product's `item`.
   */
  item: string;
}
/**
 * Moves one thing between what they carry and the stash, at Aris's lockers: of a stack, as
 * much as fits under the stash's limit or their carry limit, and what doesn't fit stays where it
 * was. The server ignores it away from the lockers, if they don't have it, or if none of it
 * fits.
 */
export interface StashMessage {
  type: 'stash';
  /**
   * What they move, by its `id`: the first of that id.
   */
  item: string;
  /**
   * `store` puts it in the stash, and `take` takes it out.
   */
  action: 'store' | 'take';
}
