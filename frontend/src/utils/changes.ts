import {
    RESOURCES,
    type Building,
    type Cards,
    type GameView,
    type HexCoords,
    type Position,
    type PublicState,
    type Road,
} from '../types/game';
import { getVertexCoords, hexCorners } from './hexLayout';

/** What one roll of the dice did, seen from the difference of two states. */
export interface RollChanges {
    total: number;
    /** Tiles with the rolled number, free of the robber and touching a building. */
    producing: HexCoords[];
    /** Resource cards gained per seat; seats that gained nothing are left out. */
    cardGains: Record<number, number>;
    /** What the own hand gained, per resource. */
    ownGains: Cards;
}

/** Pieces that appeared since the previous state. */
export interface BuiltChanges {
    roads: Road[];
    settlements: Building[];
    /** Settlements that became cities. */
    cities: Building[];
    /** Where the robber went, if it moved. */
    robber: HexCoords | null;
}

export interface StateChanges {
    roll: RollChanges | null;
    built: BuiltChanges;
}

export const NO_BUILT: BuiltChanges = { roads: [], settlements: [], cities: [], robber: null };

export const NO_CHANGES: StateChanges = { roll: null, built: NO_BUILT };

export const positionKey = ({ hex, direction }: Position) => `${hex.q},${hex.r},${direction}`;

export const hexKey = (hex: HexCoords) => `${hex.q},${hex.r}`;

const sameHex = (a: HexCoords | null, b: HexCoords | null) =>
    a === b || (a !== null && b !== null && a.q === b.q && a.r === b.r);

/**
 * The lines added to the log between two states. The server keeps only the last
 * entries, so the old log may have lost lines at its start: the new lines are
 * what follows the longest end of the old log that starts the new one.
 */
export const newLogLines = (previous: string[], next: string[]): string[] => {
    for (let dropped = 0; dropped <= previous.length; dropped++) {
        const kept = previous.length - dropped;
        if (kept > next.length) continue;
        let matches = true;
        for (let index = 0; index < kept; index++) {
            if (previous[dropped + index] !== next[index]) {
                matches = false;
                break;
            }
        }
        if (matches) return next.slice(kept);
    }
    return next;
};

/** Whether a roll happened between two game views, by the log line the server writes for it. */
export const hasNewRoll = (previous: GameView, next: GameView, names: string[]): boolean => {
    if (next.dice_roll === null) return false;
    const line = (name: string) => `${name} rolled ${next.dice_roll}.`;
    const added = newLogLines(previous.log, next.log);
    if (added.some((entry) => names.some((name) => entry === line(name)))) return true;
    // Without a readable log, the dice showing up again still tells a roll
    return previous.dice_roll === null;
};

const touches = (tile: HexCoords, building: Position) => {
    const at = getVertexCoords(building);
    return hexCorners(tile).some(({ x, y }) => Math.hypot(x - at.x, y - at.y) < 1);
};

export const producingTiles = (game: GameView, total: number): HexCoords[] => {
    if (total === 7) return [];
    return game.board_tiles
        .filter((tile) => tile.number === total && !sameHex(tile.hex, game.robber_hex))
        .filter((tile) => game.settlements.some((building) => touches(tile.hex, building)))
        .map((tile) => tile.hex);
};

const cardCounts = (state: PublicState): Map<number, number> =>
    new Map(state.players.map((player) => [player.seat, 'card_count' in player ? player.card_count : 0]));

export const cardGains = (previous: PublicState, next: PublicState): Record<number, number> => {
    const before = cardCounts(previous);
    const gains: Record<number, number> = {};
    for (const [seat, count] of cardCounts(next)) {
        const gain = count - (before.get(seat) ?? count);
        if (gain > 0) gains[seat] = gain;
    }
    return gains;
};

export const resourceGains = (previous: Cards, next: Cards): Cards => {
    const gains: Cards = {};
    for (const resource of RESOURCES) {
        const gain = (next[resource] ?? 0) - (previous[resource] ?? 0);
        if (gain > 0) gains[resource] = gain;
    }
    return gains;
};

export const builtPieces = (previous: GameView, next: GameView): BuiltChanges => {
    const oldRoads = new Set(previous.roads.map(positionKey));
    const oldBuildings = new Map(previous.settlements.map((building) => [positionKey(building), building]));

    const roads = next.roads.filter((road) => !oldRoads.has(positionKey(road)));
    const settlements = next.settlements.filter((building) => !oldBuildings.has(positionKey(building)));
    const cities = next.settlements.filter(
        (building) => building.type === 'city' && oldBuildings.get(positionKey(building))?.type === 'settlement',
    );
    const robber = next.robber_hex !== null && !sameHex(previous.robber_hex, next.robber_hex)
        ? next.robber_hex
        : null;

    return { roads, settlements, cities, robber };
};

export const isEmptyBuilt = ({ roads, settlements, cities, robber }: BuiltChanges) =>
    roads.length === 0 && settlements.length === 0 && cities.length === 0 && robber === null;

/**
 * Everything worth pointing out between two consecutive states. A state of
 * another game (a rematch) or without a running game has no changes.
 */
export const diffStates = (
    previous: PublicState,
    next: PublicState,
    previousCards: Cards = {},
    nextCards: Cards = {},
): StateChanges => {
    if (previous.room_id !== next.room_id || previous.game === null || next.game === null) return NO_CHANGES;
    if (next.version <= previous.version) return NO_CHANGES;

    const names = next.players.map((player) => player.name);
    const roll = hasNewRoll(previous.game, next.game, names) && next.game.dice_roll !== null
        ? {
            total: next.game.dice_roll,
            producing: producingTiles(next.game, next.game.dice_roll),
            cardGains: cardGains(previous, next),
            ownGains: resourceGains(previousCards, nextCards),
        }
        : null;

    return { roll, built: builtPieces(previous.game, next.game) };
};
