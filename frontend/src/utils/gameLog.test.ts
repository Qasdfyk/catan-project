import { describe, expect, it } from 'vitest';
import { logKind, splitNames } from './gameLog';
import type { Player } from '../types/game';

const player = (seat: number, name: string): Player => ({
    seat,
    name,
    is_bot: false,
    bot_level: null,
    color: 'red',
    victory_points: 0,
    card_count: 0,
    road_length: 0,
    pending_discard: 0,
    dev_card_count: 0,
    knights_played: 0,
});

const ANN = player(0, 'Ann');
const ANNA = player(1, 'Anna');
const BOT = player(2, 'Bot (2)');

describe('game log kinds', () => {
    it.each([
        ["Ann's turn.", 'turn'],
        ['Ann rolled 8.', 'roll'],
        ['Ann built a road.', 'build'],
        ['Ann built a settlement.', 'build'],
        ['Ann built a city.', 'build'],
        ['Ann traded 4 wood for 1 ore.', 'trade'],
        ['Ann offers a trade.', 'trade'],
        ['Ann traded with Anna.', 'trade'],
        ['Ann moved the robber.', 'robber'],
        ['Ann stole a card from Anna.', 'robber'],
        ['Ann discarded 4 cards.', 'discard'],
        ['Ann bought a development card.', 'card'],
        ['Ann played a Knight.', 'card'],
        ['Ann played Road Building.', 'card'],
        ['Ann played Year of Plenty.', 'card'],
        ['Ann played Monopoly on wood and took 3.', 'card'],
        ['Ann has the Longest Road (5).', 'longest_road'],
        ['Ann has the Largest Army (3).', 'largest_army'],
        ['Ann ran out of time.', 'timeout'],
        ['The bank has too little ore to pay out.', 'bank'],
        ['Ann won the game!', 'win'],
        ['Something new happened.', 'other'],
    ])('reads "%s" as %s', (entry, kind) => {
        expect(logKind(entry)).toBe(kind);
    });
});

describe('player names in the log', () => {
    it('marks every name in the entry', () => {
        expect(splitNames('Ann stole a card from Anna.', [ANN, ANNA])).toEqual([
            { text: 'Ann', player: ANN },
            { text: ' stole a card from ' },
            { text: 'Anna', player: ANNA },
            { text: '.' },
        ]);
    });

    it('does not find a name inside a longer word', () => {
        expect(splitNames('Anna rolled 6.', [ANN])).toEqual([{ text: 'Anna rolled 6.' }]);
    });

    it('takes names with special characters literally', () => {
        expect(splitNames("Bot (2)'s turn.", [BOT, ANN])).toEqual([
            { text: 'Bot (2)', player: BOT },
            { text: "'s turn." },
        ]);
    });

    it('leaves entries without names alone', () => {
        expect(splitNames('The bank has too little ore to pay out.', [ANN])).toEqual([
            { text: 'The bank has too little ore to pay out.' },
        ]);
        expect(splitNames('Ann rolled 6.', [])).toEqual([{ text: 'Ann rolled 6.' }]);
    });
});
