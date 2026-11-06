import type { GameView, Player } from '../types/game';

export interface TurnPrompt {
    /** Whose move it is, shown with their colour; null once the game is over. */
    player: Player | null;
    /** "Your turn", "You" or the player's name. */
    label: string;
    /** What to do now, or what the others are doing. The browser check matches this text. */
    text: string;
    /** The viewer has something to do. */
    act: boolean;
}

const cards = (count: number) => `${count} ${count === 1 ? 'card' : 'cards'}`;

const yourMove = (game: GameView): string => {
    switch (game.turn_phase) {
        case 'setup':
            return game.setup_waiting_for_road
                ? 'Place a road next to your new settlement.'
                : 'Place a settlement.';
        case 'roll_dice':
            return 'Roll the dice.';
        case 'move_robber':
            return 'Move the robber to another tile.';
        case 'steal':
            return 'Choose a player to steal from.';
        case 'road_building':
            return `Place a free road (${game.free_roads_left} left).`;
        default:
            return 'Build, trade or end your turn.';
    }
};

const theirMove = (game: GameView): string => {
    switch (game.turn_phase) {
        case 'setup':
            return 'is placing pieces…';
        case 'roll_dice':
            return 'is about to roll…';
        case 'move_robber':
            return 'is moving the robber…';
        case 'steal':
            return 'is choosing whom to rob…';
        case 'road_building':
            return 'is placing free roads…';
        default:
            return 'is building and trading…';
    }
};

/** What the top bar tells this seat: whose turn it is and what can be done now. */
export const turnPrompt = (
    game: GameView, players: Player[], seat: number, mustDiscard: number,
): TurnPrompt => {
    if (game.winner_seat !== null) {
        return { player: null, label: '', text: `${players[game.winner_seat].name} won the game!`, act: false };
    }

    const current = players[game.current_seat];
    const isMyTurn = game.current_seat === seat && !game.is_game_over;
    const label = isMyTurn ? 'Your turn' : current.name;

    if (mustDiscard > 0) {
        return { player: players[seat], label: 'You', text: `Discard ${cards(mustDiscard)}.`, act: true };
    }
    if (game.turn_phase === 'discard') {
        return { player: current, label, text: 'Waiting for players to discard…', act: false };
    }
    if (!isMyTurn) return { player: current, label, text: theirMove(game), act: false };
    return { player: current, label, text: yourMove(game), act: true };
};
