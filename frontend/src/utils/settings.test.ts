import { describe, expect, it } from 'vitest';
import { sameSettings, settingsSummary, STANDARD_SETTINGS, TWO_PLAYER_SETTINGS } from './settings';

describe('settings', () => {
    it('compares every setting', () => {
        expect(sameSettings(STANDARD_SETTINGS, { ...STANDARD_SETTINGS })).toBe(true);
        expect(sameSettings(STANDARD_SETTINGS, TWO_PLAYER_SETTINGS)).toBe(false);
        expect(sameSettings(TWO_PLAYER_SETTINGS, { ...TWO_PLAYER_SETTINGS, turn_seconds: 90 })).toBe(false);
        expect(sameSettings(TWO_PLAYER_SETTINGS, { ...TWO_PLAYER_SETTINGS, desert: 'center' })).toBe(false);
    });

    it('keeps the standard rules short', () => {
        expect(settingsSummary(STANDARD_SETTINGS)).toBe('First to 10 · Discard above 7');
    });

    it('lists every rule that differs from the standard', () => {
        expect(settingsSummary({
            victory_points: 8,
            discard_limit: 9,
            desert: 'center',
            friendly_robber: true,
            turn_seconds: 90,
        })).toBe('First to 8 · Discard above 9 · Desert in the centre · Friendly robber · 90 s turns');
    });
});
