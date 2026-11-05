import type { BotLevel } from '../types/game';

// The levels the host can pick. Hard joins the list when its strategy lands.
export const BOT_LEVELS: BotLevel[] = ['easy', 'medium'];

export const BOT_LEVEL_LABELS: Record<BotLevel, string> = {
    easy: 'Easy',
    medium: 'Medium',
    hard: 'Hard',
};

/** The levels to offer for a bot; one set some other way stays listed, so the select shows it. */
export const botLevelOptions = (current: BotLevel | null): BotLevel[] =>
    current === null || BOT_LEVELS.includes(current) ? BOT_LEVELS : [...BOT_LEVELS, current];

/** "bot, easy", or just "bot" when the server sent no level. */
export const botLabel = (level: BotLevel | null) => (level === null ? 'bot' : `bot, ${level}`);
