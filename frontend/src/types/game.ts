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

export interface LobbyPlayer {
  seat: number;
  name: string;
}

export interface Player extends LobbyPlayer {
  color: PlayerColor;
  victory_points: number;
  card_count: number;
  road_length: number;
  pending_discard: number;
}

export interface GameView {
  turn_phase: TurnPhase;
  dice_roll: number | null;
  setup_waiting_for_road: boolean;
  robber_hex: HexCoords | null;
  is_game_over: boolean;
  board_tiles: BoardTile[];
  ports: Port[];
  roads: Road[];
  settlements: Building[];
  longest_road_holder: PlayerColor | null;
  log: string[];
  current_seat: number;
  winner_seat: number | null;
}

export interface PublicState {
  room_id: string;
  version: number;
  status: RoomStatus;
  host_seat: number;
  players: (LobbyPlayer | Player)[];
  game: GameView | null;
}

export interface LegalMoves {
  settlements: Position[];
  roads: Position[];
  cities: Position[];
  robber_hexes: HexCoords[];
  steal_targets: number[];
  must_discard: number;
}

export interface PrivateState {
  seat: number;
  resources: Partial<Record<Resource, number>>;
  trade_rates?: Record<Resource, number>;
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
