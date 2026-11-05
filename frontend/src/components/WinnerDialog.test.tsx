import { renderToStaticMarkup } from 'react-dom/server';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it } from 'vitest';
import { WinnerDialog } from './WinnerDialog';
import type { Player } from '../types/game';

const player = (seat: number, name: string, points: number): Player => ({
    seat,
    name,
    is_bot: false,
    bot_level: null,
    color: 'red',
    victory_points: points,
    card_count: 0,
    road_length: 0,
    pending_discard: 0,
    dev_card_count: 0,
    knights_played: 0,
});

const PLAYERS = [player(0, 'Ann', 10), player(1, 'Bob', 7)];

// No DOM in the test setup: the dialog is rendered to markup and checked as text.
const render = (isHost: boolean, rematchStarted = false, rematchError = '') => renderToStaticMarkup(
    <MemoryRouter>
        <WinnerDialog
            winner={PLAYERS[0]}
            players={PLAYERS}
            isHost={isHost}
            rematchStarted={rematchStarted}
            rematchError={rematchError}
            onRematch={() => {}}
            onClose={() => {}}
        />
    </MemoryRouter>,
);

const button = (markup: string, label: string) => markup.match(new RegExp(`<button[^>]*>${label}</button>`))?.[0] ?? '';

describe('WinnerDialog', () => {
    it('lets the host start a rematch', () => {
        const markup = render(true);

        expect(button(markup, 'Rematch')).toContain('class="primary"');
        expect(button(markup, 'Rematch')).not.toContain('disabled');
        expect(markup).toContain('New game');
        expect(markup).toContain('See the board');
        expect(markup).not.toContain('Waiting for the host');
    });

    it('tells the other players to wait for the host', () => {
        const markup = render(false);

        expect(button(markup, 'Rematch')).toBe('');
        expect(markup).toContain('Waiting for the host to start a rematch…');
        expect(markup).toContain('New game');
        expect(markup).toContain('See the board');
    });

    it('shows the rematch is on its way', () => {
        const markup = render(true, true);

        expect(button(markup, 'Rematch')).toContain('disabled');
        expect(markup).toContain('Joining the rematch…');
    });

    it('shows why joining the rematch failed', () => {
        const markup = render(false, true, 'There is no rematch yet.');

        expect(markup).toContain('role="alert"');
        expect(markup).toContain('There is no rematch yet.');
        expect(markup).not.toContain('Joining the rematch…');
    });
});
