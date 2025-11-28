/**
 * TYPE DEFINITIONS
 * Synced with backend/app/services/serializer.py
 */

export const ResourceType = {
  WOOD: "wood",
  BRICK: "brick",
  SHEEP: "sheep",
  WHEAT: "wheat",
  ORE: "ore",
  DESERT: "desert"
} as const;
export type ResourceType = (typeof ResourceType)[keyof typeof ResourceType];

export const PlayerColor = {
  RED: "red",
  BLUE: "blue",
  WHITE: "white",
  ORANGE: "orange"
} as const;
export type PlayerColor = (typeof PlayerColor)[keyof typeof PlayerColor];

export const TurnPhase = {
  SETUP: "setup",       // <--- ADDED THIS
  ROLL_DICE: "roll_dice",
  MAIN_PHASE: "main_phase"
} as const;
export type TurnPhase = (typeof TurnPhase)[keyof typeof TurnPhase];

export const BuildingType = {
  SETTLEMENT: "settlement",
  CITY: "city"
} as const;
export type BuildingType = (typeof BuildingType)[keyof typeof BuildingType];

// --- CORE VALUE OBJECTS ---

export interface HexCoords {
  q: number;
  r: number;
  s: number;
}

export interface BoardTile {
  hex: HexCoords;
  resource: ResourceType;
  number: number | null;
}

export interface Road {
  hex: HexCoords;
  direction: number;
  color: PlayerColor;
}

export interface Settlement {
  hex: HexCoords;
  direction: number;
  owner: PlayerColor;
  type: BuildingType;
}

export interface Player {
  id: string;
  name: string;
  color: PlayerColor;
  resources: Partial<Record<ResourceType, number>>;
  victory_points: number;
}

export interface GameState {
  players: Player[];
  current_turn_index: number;
  turn_phase: TurnPhase;
  dice_roll: number | null;
  robber_hex: HexCoords | null;
  is_game_over: boolean;
  winner_name: string | null;
  

  setup_waiting_for_road?: boolean;

  // Board State
  board_tiles: BoardTile[];
  roads: Road[];
  settlements: Settlement[];
}

export interface GameCreateResponse {
  room_id: string;
  status: string;
  created_at: string;
  players: Player[];
}