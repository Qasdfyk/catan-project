import { describe, expect, it } from 'vitest';
import { botLabel, botLevelOptions, BOT_LEVELS } from './bots';

describe('bots', () => {
    it('offers the levels whose strategy exists', () => {
        expect(botLevelOptions('medium')).toEqual(['easy', 'medium']);
        expect(botLevelOptions(null)).toBe(BOT_LEVELS);
    });

    it('keeps a level that is not offered yet', () => {
        expect(botLevelOptions('hard')).toEqual(['easy', 'medium', 'hard']);
    });

    it('names the level of a bot', () => {
        expect(botLabel('easy')).toBe('bot, easy');
        expect(botLabel(null)).toBe('bot');
    });
});
