import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { GameLog } from './GameLog';
import type { Player, PlayerColor } from '../types/game';
import { PLAYER_TEXT_COLORS } from '../utils/labels';

const player = (seat: number, name: string, color: PlayerColor): Player => ({
    seat,
    name,
    is_bot: false,
    bot_level: null,
    color,
    victory_points: 0,
    card_count: 0,
    road_length: 0,
    pending_discard: 0,
    dev_card_count: 0,
    knights_played: 0,
});

const PLAYERS = [player(0, 'Ann', 'red'), player(1, 'Bob', 'blue')];

// No DOM in the test setup: the log is rendered to markup and checked as text.
const render = (log: string[]) => renderToStaticMarkup(<GameLog log={log} players={PLAYERS} />);

describe('GameLog', () => {
    it('shows the newest entry first', () => {
        const markup = render(['Ann rolled 8.', 'Ann built a road.']);

        expect(markup.indexOf('built a road')).toBeLessThan(markup.indexOf('rolled 8'));
    });

    it('marks each entry with its kind', () => {
        const markup = render(['Ann rolled 8.', 'Bob stole a card from Ann.']);

        expect(markup).toContain('class="log-roll"');
        expect(markup).toContain('class="log-robber"');
        expect(markup).toContain('title="Dice roll"');
    });

    it('writes the names in the colours of the players', () => {
        const markup = render(['Bob traded with Ann.']);

        expect(markup).toContain(`<strong class="log-player" style="color:${PLAYER_TEXT_COLORS.blue}">Bob</strong>`);
        expect(markup).toContain(`<strong class="log-player" style="color:${PLAYER_TEXT_COLORS.red}">Ann</strong>`);
    });
});
