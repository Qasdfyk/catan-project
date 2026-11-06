import type { Player } from '../types/game';

export type LogKind =
    | 'turn' | 'roll' | 'build' | 'trade' | 'robber' | 'discard' | 'card'
    | 'longest_road' | 'largest_army' | 'timeout' | 'bank' | 'win' | 'other';

/** Matched against the sentences of the game log in backend/app/models/game.py, in this order. */
const KINDS: [LogKind, RegExp][] = [
    ['win', / won the game!$/],
    ['turn', /'s turn\.$/],
    ['timeout', / ran out of time\.$/],
    ['roll', / rolled \d+\.$/],
    ['build', / built a (road|settlement|city)\.$/],
    ['discard', / discarded \d+ cards?\.$/],
    ['robber', / moved the robber\.$| stole a card from /],
    ['card', / bought a development card\.$| played (a Knight|Road Building|Year of Plenty|Monopoly)/],
    ['longest_road', / has the Longest Road /],
    ['largest_army', / has the Largest Army /],
    ['trade', / traded | offers a trade\.$/],
    ['bank', /^The bank has too little /],
];

/** A short glyph and a name for each kind of event; the glyphs avoid emoji so they take the text colour. */
export const LOG_ICONS: Record<LogKind, { glyph: string; label: string }> = {
    turn: { glyph: '▸', label: 'New turn' },
    roll: { glyph: '⚄', label: 'Dice roll' },
    build: { glyph: '⌂', label: 'Building' },
    trade: { glyph: '⇄', label: 'Trade' },
    robber: { glyph: '♟\uFE0E', label: 'Robber' },
    discard: { glyph: '✕', label: 'Discard' },
    card: { glyph: '▤', label: 'Development card' },
    longest_road: { glyph: '═', label: 'Longest Road' },
    largest_army: { glyph: '⚑', label: 'Largest Army' },
    timeout: { glyph: '⧗', label: 'Out of time' },
    bank: { glyph: '!', label: 'Bank' },
    win: { glyph: '★', label: 'Victory' },
    other: { glyph: '·', label: 'Event' },
};

export const logKind = (entry: string): LogKind =>
    KINDS.find(([, pattern]) => pattern.test(entry))?.[0] ?? 'other';

export interface LogPart {
    text: string;
    /** Set when the text is a player's name. */
    player?: Player;
}

const escape = (text: string) => text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');

/**
 * Splits an entry around the names of the players. Longer names are tried
 * first and a name must stand as a whole word, so "Ann" doesn't match in "Anna".
 */
export const splitNames = (entry: string, players: Player[]): LogPart[] => {
    const named = players.filter((player) => player.name.length > 0);
    if (named.length === 0) return [{ text: entry }];

    const names = [...named].sort((a, b) => b.name.length - a.name.length).map((player) => escape(player.name));
    const pattern = new RegExp(`(?<![\\p{L}\\p{N}_])(${names.join('|')})(?![\\p{L}\\p{N}_])`, 'gu');

    const parts: LogPart[] = [];
    let last = 0;
    for (const match of entry.matchAll(pattern)) {
        const start = match.index ?? 0;
        if (start > last) parts.push({ text: entry.slice(last, start) });
        parts.push({ text: match[0], player: named.find((player) => player.name === match[0]) });
        last = start + match[0].length;
    }
    if (last < entry.length) parts.push({ text: entry.slice(last) });
    return parts;
};
