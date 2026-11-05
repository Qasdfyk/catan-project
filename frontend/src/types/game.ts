/**
 * TYPE DEFINITIONS
 * Synced with backend/app/services/views.py
 */

export const RESOURCES = ['wood', 'brick', 'sheep', 'wheat', 'ore'] as const;
export type Resource = (typeof RESOURCES)[number];
export type TileResource = Resource | 'desert';

export type PlayerColor = 'red' | 'blue' | 'white' | 'orange';

export type TurnPhase =
  | 'setup'
  | 'roll_dice'
  | 'discard'
  | 'move_robber'
  | 'steal'
  | 'road_building'
  | 'main_phase';

export type RoomStatus = 'lobby' | 'playing' | 'finished';

export interface HexCoords {
  q: number;
  r: number;
  s: number;
}

/** A vertex or an edge, identified by its canonical hex and direction. */
export interface Position {
  hex: HexCoords;
  direction: number;
}

export interface BoardTile {
  hex: HexCoords;
  resource: TileResource;
  number: number | null;
}

export interface Port {
  type: string;
  vertices: Position[];
}

export interface Road extends Position {
  color: PlayerColor;
}

export interface Building extends Position {
  owner: PlayerColor;
  type: 'settlement' | 'city';
}

export type DevCard = 'knight' | 'victory_point' | 'road_building' | 'year_of_plenty' | 'monopoly';

export type Cards = Partial<Record<Resource, number>>;

export type BotLevel = 'easy' | 'medium' | 'hard';

export interface LobbyPlayer {
  seat: number;
  name: string;
  is_bot: boolean;
  /** How well the bot plays; null for people. */
  bot_level: BotLevel | null;
}

export interface Player extends LobbyPlayer {
  color: PlayerColor;
  victory_points: number;
  card_count: number;
  road_length: number;
  pending_discard: number;
  dev_card_count: number;
  knights_played: number;
}

export interface TradeOffer {
  proposer_seat: number;
  give: Cards;
  get: Cards;
  accepted_seats: number[];
  declined_seats: number[];
}

export interface GameView {
  turn_phase: TurnPhase;
  dice_roll: number | null;
  dice: number[];
  setup_waiting_for_road: boolean;
  robber_hex: HexCoords | null;
  is_game_over: boolean;
  board_tiles: BoardTile[];
  ports: Port[];
  roads: Road[];
  settlements: Building[];
  longest_road_holder: PlayerColor | null;
  largest_army_holder: PlayerColor | null;
  free_roads_left: number;
  bank: Record<Resource, number>;
  dev_deck_count: number;
  trade_offer: TradeOffer | null;
  log: string[];
  current_seat: number;
  winner_seat: number | null;
}

export type DesertPlacement = 'random' | 'center';

/** Chosen by the host in the lobby; fixed once the game starts. */
export interface GameSettings {
  victory_points: number;
  /** On a 7, players holding more cards than this discard half. */
  discard_limit: number;
  desert: DesertPlacement;
  /** The robber can't target opponents with 2 or fewer visible points. */
  friendly_robber: boolean;
  turn_seconds: number | null;
}

export interface PublicState {
  room_id: string;
  version: number;
  status: RoomStatus;
  host_seat: number;
  players: (LobbyPlayer | Player)[];
  settings: GameSettings;
  game: GameView | null;
  /** Epoch seconds when the waited-on players run out of time; null without a timer. */
  turn_deadline: number | null;
  /** The server's epoch seconds when this state was produced, to correct clock skew. */
  server_time: number;
  /** The room the host opened for a rematch, once there is one. */
  rematch_room_id: string | null;
}

export interface LegalMoves {
  settlements: Position[];
  roads: Position[];
  cities: Position[];
  robber_hexes: HexCoords[];
  steal_targets: number[];
  must_discard: number;
  can_buy_dev_card: boolean;
  playable_dev_cards: DevCard[];
}

export interface PrivateState {
  seat: number;
  resources: Cards;
  trade_rates?: Record<Resource, number>;
  dev_cards?: DevCard[];
  hidden_points?: number;
  legal: LegalMoves | null;
}

export interface RoomSession {
  room_id: string;
  token: string;
  seat: number;
}

export interface RoomSummary {
  room_id: string;
  status: RoomStatus;
  players: { name: string; online: boolean }[];
}

export interface ChatMessage {
  seat: number;
  text: string;
  sent_at: number;
}
