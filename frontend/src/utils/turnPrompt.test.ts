import { describe, expect, it } from 'vitest';
import { turnPrompt } from './turnPrompt';
import type { GameView, Player, TurnPhase } from '../types/game';

const player = (seat: number, name: string): Player => ({
    seat,
    name,
    is_bot: false,
    bot_level: null,
    color: seat === 0 ? 'red' : 'blue',
    victory_points: 2,
    card_count: 0,
    road_length: 0,
    pending_discard: 0,
    dev_card_count: 0,
    knights_played: 0,
});

const PLAYERS = [player(0, 'Ann'), player(1, 'Bob')];

const game = (turn_phase: TurnPhase, extra: Partial<GameView> = {}) => ({
    turn_phase,
    current_seat: 0,
    winner_seat: null,
    is_game_over: false,
    setup_waiting_for_road: false,
    free_roads_left: 0,
    ...extra,
}) as GameView;

describe('turn prompt', () => {
    it('tells the current player what to do', () => {
        expect(turnPrompt(game('roll_dice'), PLAYERS, 0, 0)).toEqual({
            player: PLAYERS[0], label: 'Your turn', text: 'Roll the dice.', act: true,
        });
        expect(turnPrompt(game('main_phase'), PLAYERS, 0, 0).text).toBe('Build, trade or end your turn.');
        expect(turnPrompt(game('move_robber'), PLAYERS, 0, 0).text).toBe('Move the robber to another tile.');
        expect(turnPrompt(game('steal'), PLAYERS, 0, 0).text).toBe('Choose a player to steal from.');
        expect(turnPrompt(game('road_building', { free_roads_left: 2 }), PLAYERS, 0, 0).text)
            .toBe('Place a free road (2 left).');
    });

    it('walks through the setup', () => {
        expect(turnPrompt(game('setup'), PLAYERS, 0, 0).text).toBe('Place a settlement.');
        expect(turnPrompt(game('setup', { setup_waiting_for_road: true }), PLAYERS, 0, 0).text)
            .toBe('Place a road next to your new settlement.');
    });

    it('names the player the others wait for', () => {
        expect(turnPrompt(game('roll_dice'), PLAYERS, 1, 0)).toEqual({
            player: PLAYERS[0], label: 'Ann', text: 'is about to roll…', act: false,
        });
        expect(turnPrompt(game('setup'), PLAYERS, 1, 0).text).toBe('is placing pieces…');
        expect(turnPrompt(game('main_phase'), PLAYERS, 1, 0).text).toBe('is building and trading…');
    });

    it('asks any player over the limit to discard', () => {
        const prompt = turnPrompt(game('discard'), PLAYERS, 1, 4);

        expect(prompt).toEqual({ player: PLAYERS[1], label: 'You', text: 'Discard 4 cards.', act: true });
        expect(turnPrompt(game('discard'), PLAYERS, 1, 1).text).toBe('Discard 1 card.');
    });

    it('waits for the others to discard', () => {
        const prompt = turnPrompt(game('discard'), PLAYERS, 0, 0);

        expect(prompt.text).toBe('Waiting for players to discard…');
        expect(prompt.act).toBe(false);
    });

    it('announces the winner', () => {
        const prompt = turnPrompt(game('main_phase', { winner_seat: 1, is_game_over: true }), PLAYERS, 0, 0);

        expect(prompt).toEqual({ player: null, label: '', text: 'Bob won the game!', act: false });
    });
});
