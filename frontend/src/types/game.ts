/**
 * TYPE DEFINITIONS
 * Synced with backend/app/services/serializer.py and backend/app/schemas/game_schemas.py
 */

// --- CONSTANTS (Replaces Enums for 'erasableSyntaxOnly' compatibility) ---

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

// Maps to Hex object in app/models/hex_lib.py serialized via _hex_to_dict
export interface HexCoords {
  q: number;
  r: number;
  s: number;
}

// --- BOARD ENTITIES (from serializer lists) ---

export interface BoardTile {
  hex: HexCoords;
  resource: ResourceType;
  number: number | null; // Null for Desert
}

// Edge representation in JSON: { hex: HexCoords, direction: int, color: string }
export interface Road {
  hex: HexCoords;
  direction: number; // 0-5
  color: PlayerColor;
}

// Vertex representation in JSON: { hex: HexCoords, direction: int, owner: string, type: string }
export interface Settlement {
  hex: HexCoords;
  direction: number; // 0-5
  owner: PlayerColor;
  type: BuildingType;
}

// --- PLAYER & GAME STATE ---

export interface Player {
  id: string;
  name: string;
  color: PlayerColor;
  // Python Counter creates a dict. Keys might be missing if count is 0,
  // so we use Partial, or we assume backend sends 0s.
  resources: Partial<Record<ResourceType, number>>;
  victory_points: number;
}

// The full state broadcasted via WebSocket (app/services/serializer.py -> game_to_dict)
export interface GameState {
  players: Player[];
  current_turn_index: number;
  turn_phase: TurnPhase;
  dice_roll: number | null;
  robber_hex: HexCoords | null;
  is_game_over: boolean;
  winner_name: string | null;
  
  // Board State
  board_tiles: BoardTile[];
  roads: Road[];
  settlements: Settlement[];
}

// --- REST API RESPONSES (app/schemas/game_schemas.py) ---

// Response from POST /api/games
export interface GameCreateResponse {
  room_id: string;
  status: string;
  created_at: string;
  players: string[]; // REST API returns names only strings initially
}