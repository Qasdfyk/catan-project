import { renderToStaticMarkup } from 'react-dom/server';
import { afterAll, beforeAll, describe, expect, it, vi } from 'vitest';
import { LobbyScreen } from './LobbyScreen';
import type { RoomConnection } from '../net/useRoom';
import type { BotLevel, LobbyPlayer, PublicState } from '../types/game';
import { STANDARD_SETTINGS } from '../utils/settings';

const player = (seat: number, name: string, botLevel: BotLevel | null = null): LobbyPlayer => ({
    seat,
    name,
    is_bot: botLevel !== null,
    bot_level: botLevel,
});

const state = (players: LobbyPlayer[]): PublicState => ({
    room_id: 'room1234',
    version: 1,
    status: 'lobby',
    host_seat: 0,
    players,
    settings: STANDARD_SETTINGS,
    game: null,
    turn_deadline: null,
    server_time: 0,
    rematch_room_id: null,
});

const ROOM = { online: [], error: null, send: () => {} } as unknown as RoomConnection;

const PLAYERS = [player(0, 'Ann'), player(1, 'Bob'), player(2, 'Ada', 'easy'), player(3, 'Boole', 'hard')];

// No DOM in the test setup: the lobby is rendered to markup and checked as text.
const render = (seat: number) => renderToStaticMarkup(<LobbyScreen state={state(PLAYERS)} seat={seat} room={ROOM} />);

const select = (markup: string, name: string) =>
    markup.match(new RegExp(`<select[^>]*aria-label="Level of ${name}"[^>]*>.*?</select>`))?.[0] ?? '';

describe('LobbyScreen', () => {
    beforeAll(() => vi.stubGlobal('window', { location: { href: 'http://localhost/room/room1234' } }));
    afterAll(() => vi.unstubAllGlobals());

    it('lets the host choose the level of each bot', () => {
        const markup = render(0);

        expect(markup.match(/class="bot-level"/g)).toHaveLength(2);
        const easy = select(markup, 'Ada');
        expect(easy).toContain('<option value="easy" selected="">Easy</option>');
        expect(easy).toContain('<option value="medium">Medium</option>');
        expect(easy).toContain('<option value="hard">Hard</option>');
    });

    it('selects the level each bot has', () => {
        expect(select(render(0), 'Boole')).toContain('<option value="hard" selected="">Hard</option>');
    });

    it('shows guests the level as text', () => {
        const markup = render(1);

        expect(markup).not.toContain('<select');
        expect(markup).toContain(' · bot, easy');
        expect(markup).toContain(' · bot, hard');
    });

    it('shows bots as ready rather than offline', () => {
        const markup = render(1);

        expect(markup.match(/class="dot bot"/g)).toHaveLength(2);
        // Ann and Bob are people who have not connected in this test
        expect(markup.match(/class="dot"/g)).toHaveLength(2);
    });
});
