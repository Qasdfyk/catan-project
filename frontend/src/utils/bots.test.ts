import { describe, expect, it } from 'vitest';
import { botLabel, BOT_LEVELS } from './bots';

describe('bots', () => {
    it('offers every level, weakest first', () => {
        expect(BOT_LEVELS).toEqual(['easy', 'medium', 'hard']);
    });

    it('names the level of a bot', () => {
        expect(botLabel('easy')).toBe('bot, easy');
        expect(botLabel(null)).toBe('bot');
    });
});
