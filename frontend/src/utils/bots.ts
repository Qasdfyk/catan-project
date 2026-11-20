import type { BotLevel } from '../types/game';

/** The levels the host can pick, weakest first. */
export const BOT_LEVELS: BotLevel[] = ['easy', 'medium', 'hard', 'expert'];

export const BOT_LEVEL_LABELS: Record<BotLevel, string> = {
    easy: 'Easy',
    medium: 'Medium',
    hard: 'Hard',
    // Searches its moves in catan-analysis-engine; plays as hard where the
    // bots service has no engine
    expert: 'Expert',
};

/** "bot, easy", or just "bot" when the server sent no level. */
export const botLabel = (level: BotLevel | null) => (level === null ? 'bot' : `bot, ${level}`);
