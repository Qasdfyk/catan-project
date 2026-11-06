import { describe, expect, it } from 'vitest';
import {
    builtPieces,
    cardGains,
    diffStates,
    hasNewRoll,
    isEmptyBuilt,
    newLogLines,
    producingTiles,
    resourceGains,
} from './changes';
import type { Building, GameView, Player, PublicState } from '../types/game';
import { STANDARD_SETTINGS } from './settings';

const CENTER = { q: 0, r: 0, s: 0 };
const NORTH_EAST = { q: 1, r: -1, s: 0 };
const EAST = { q: 1, r: 0, s: -1 };
const SOUTH = { q: 0, r: 1, s: -1 };

// The corner shared by the center, north-east and east tiles
const SHARED_CORNER: Building = { hex: CENTER, direction: 0, owner: 'red', type: 'settlement' };

const game = (changes: Partial<GameView> = {}): GameView => ({
    turn_phase: 'roll_dice',
    dice_roll: null,
    dice: [],
    setup_waiting_for_road: false,
    robber_hex: null,
    is_game_over: false,
    board_tiles: [
        { hex: CENTER, resource: 'wood', number: 8 },
        { hex: NORTH_EAST, resource: 'ore', number: 8 },
        { hex: EAST, resource: 'brick', number: 5 },
        { hex: SOUTH, resource: 'wheat', number: 8 },
    ],
    ports: [],
    roads: [],
    settlements: [SHARED_CORNER],
    longest_road_holder: null,
    largest_army_holder: null,
    free_roads_left: 0,
    bank: { wood: 19, brick: 19, sheep: 19, wheat: 19, ore: 19 },
    dev_deck_count: 25,
    trade_offer: null,
    log: ["Ann's turn."],
    current_seat: 0,
    winner_seat: null,
    ...changes,
});

const player = (seat: number, name: string, cardCount: number): Player => ({
    seat,
    name,
    is_bot: false,
    bot_level: null,
    color: seat === 0 ? 'red' : 'blue',
    victory_points: 2,
    card_count: cardCount,
    road_length: 1,
    pending_discard: 0,
    dev_card_count: 0,
    knights_played: 0,
});

const state = (version: number, view: GameView | null, counts: [number, number] = [3, 3]): PublicState => ({
    room_id: 'ROOM',
    version,
    status: 'playing',
    host_seat: 0,
    players: [player(0, 'Ann', counts[0]), player(1, 'Bob', counts[1])],
    settings: STANDARD_SETTINGS,
    game: view,
    turn_deadline: null,
    server_time: 0,
    rematch_room_id: null,
});

const rolled = (total: number, log: string[] = ["Ann's turn.", `Ann rolled ${total}.`]) =>
    game({ turn_phase: 'main_phase', dice_roll: total, dice: [total - 1, 1], log });

describe('new log lines', () => {
    it('returns what was appended', () => {
        expect(newLogLines(['a', 'b'], ['a', 'b', 'c', 'd'])).toEqual(['c', 'd']);
    });

    it('returns nothing for the same log', () => {
        expect(newLogLines(['a', 'b'], ['a', 'b'])).toEqual([]);
    });

    it('follows a log that dropped its oldest lines', () => {
        expect(newLogLines(['a', 'b', 'c'], ['b', 'c', 'd'])).toEqual(['d']);
        expect(newLogLines(['a', 'b', 'c'], ['c', 'd', 'e'])).toEqual(['d', 'e']);
    });

    it('treats a repeated line as new, not as the old one', () => {
        expect(newLogLines(['x', 'y'], ['x', 'y', 'y'])).toEqual(['y']);
    });

    it('returns the whole log when nothing overlaps', () => {
        expect(newLogLines([], ['a'])).toEqual(['a']);
        expect(newLogLines(['a', 'b'], ['c', 'd'])).toEqual(['c', 'd']);
    });
});

describe('new roll', () => {
    const names = ['Ann', 'Bob'];

    it('sees the line the server writes for a roll', () => {
        expect(hasNewRoll(game(), rolled(8), names)).toBe(true);
    });

    it('sees the same number rolled twice in a row', () => {
        const first = rolled(8, ["Ann's turn.", 'Ann rolled 8.']);
        const second = rolled(8, ["Ann's turn.", 'Ann rolled 8.', "Bob's turn.", 'Bob rolled 8.']);
        expect(hasNewRoll(first, second, names)).toBe(true);
    });

    it('ignores later actions in a turn that was already rolled', () => {
        const after = rolled(8, ["Ann's turn.", 'Ann rolled 8.', 'Ann built a road.']);
        expect(hasNewRoll(rolled(8), after, names)).toBe(false);
    });

    it('ignores a name that only looks like a roll', () => {
        const before = rolled(6, ['Ann rolled 6.']);
        const after = rolled(6, ['Ann rolled 6.', 'Eve rolled 6.']);
        expect(hasNewRoll(before, after, names)).toBe(false);
    });

    it('falls back to the dice appearing when the log says nothing', () => {
        expect(hasNewRoll(game({ log: [] }), rolled(4, []), names)).toBe(true);
    });

    it('needs dice on the table', () => {
        expect(hasNewRoll(rolled(8), game({ log: ['Ann rolled 8.', "Bob's turn."] }), names)).toBe(false);
    });
});

describe('producing tiles', () => {
    it('picks the tiles with the number that touch a building', () => {
        expect(producingTiles(rolled(8), 8)).toEqual([CENTER, NORTH_EAST]);
    });

    it('leaves out the tile under the robber', () => {
        expect(producingTiles(game({ robber_hex: CENTER }), 8)).toEqual([NORTH_EAST]);
    });

    it('has nothing for a seven or an empty number', () => {
        expect(producingTiles(game(), 7)).toEqual([]);
        expect(producingTiles(game(), 11)).toEqual([]);
    });

    it('counts cities too', () => {
        const city: Building = { hex: SOUTH, direction: 1, owner: 'blue', type: 'city' };
        expect(producingTiles(game({ settlements: [city] }), 8)).toEqual([SOUTH]);
    });
});

describe('card gains', () => {
    it('reports the seats whose card count rose', () => {
        expect(cardGains(state(1, game(), [3, 3]), state(2, game(), [5, 2]))).toEqual({ 0: 2 });
    });

    it('reports the own gains per resource', () => {
        expect(resourceGains({ wood: 1, ore: 2 }, { wood: 2, ore: 4, brick: 1, sheep: 0 }))
            .toEqual({ wood: 1, ore: 2, brick: 1 });
        expect(resourceGains({ wheat: 2 }, { wheat: 1 })).toEqual({});
    });
});

describe('built pieces', () => {
    it('finds new roads and settlements', () => {
        const road = { hex: CENTER, direction: 0, color: 'red' as const };
        const settlement: Building = { hex: SOUTH, direction: 3, owner: 'blue', type: 'settlement' };
        const built = builtPieces(game(), game({ roads: [road], settlements: [SHARED_CORNER, settlement] }));

        expect(built.roads).toEqual([road]);
        expect(built.settlements).toEqual([settlement]);
        expect(built.cities).toEqual([]);
        expect(built.robber).toBeNull();
    });

    it('finds a settlement that became a city', () => {
        const city: Building = { ...SHARED_CORNER, type: 'city' };
        const built = builtPieces(game(), game({ settlements: [city] }));

        expect(built.cities).toEqual([city]);
        expect(built.settlements).toEqual([]);
    });

    it('finds where the robber went', () => {
        expect(builtPieces(game({ robber_hex: SOUTH }), game({ robber_hex: EAST })).robber).toEqual(EAST);
        expect(builtPieces(game({ robber_hex: SOUTH }), game({ robber_hex: { ...SOUTH } })).robber).toBeNull();
    });

    it('is empty when nothing was built', () => {
        expect(isEmptyBuilt(builtPieces(game(), game()))).toBe(true);
    });
});

describe('diff of two states', () => {
    it('describes a roll', () => {
        const changes = diffStates(
            state(1, game(), [3, 3]),
            state(2, rolled(8), [5, 3]),
            { wood: 1 },
            { wood: 2, ore: 1 },
        );

        expect(changes.roll).toEqual({
            total: 8,
            producing: [CENTER, NORTH_EAST],
            cardGains: { 0: 2 },
            ownGains: { wood: 1, ore: 1 },
        });
        expect(isEmptyBuilt(changes.built)).toBe(true);
    });

    it('has no roll for a build after the roll', () => {
        const road = { hex: CENTER, direction: 0, color: 'red' as const };
        const after = { ...rolled(8, ["Ann's turn.", 'Ann rolled 8.', 'Ann built a road.']), roads: [road] };
        const changes = diffStates(state(2, rolled(8)), state(3, after, [1, 3]));

        expect(changes.roll).toBeNull();
        expect(changes.built.roads).toEqual([road]);
    });

    it('has nothing for an older or the same version', () => {
        expect(diffStates(state(2, game()), state(2, rolled(8))).roll).toBeNull();
        expect(diffStates(state(3, game()), state(2, rolled(8))).roll).toBeNull();
    });

    it('has nothing across rooms or without a game', () => {
        const other = { ...state(2, rolled(8)), room_id: 'OTHER' };
        expect(diffStates(state(1, game()), other).roll).toBeNull();
        expect(diffStates(state(1, null), state(2, rolled(8))).roll).toBeNull();
    });
});
