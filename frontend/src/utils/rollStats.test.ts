import { describe, expect, it } from 'vitest';
import { combinations, expectedShare, percent, rollBars, scaleOf } from './rollStats';

describe('roll stats', () => {
    it('counts the ways two dice give each total', () => {
        expect(combinations(2)).toBe(1);
        expect(combinations(7)).toBe(6);
        expect(combinations(12)).toBe(1);
        const all = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12].reduce((sum, total) => sum + combinations(total), 0);
        expect(all).toBe(36);
    });

    it('expects a 7 once in six rolls', () => {
        expect(expectedShare(7)).toBeCloseTo(1 / 6);
        expect(expectedShare(6)).toBeCloseTo(5 / 36);
    });

    it('turns the counts into a bar per total', () => {
        const bars = rollBars([1, 0, 0, 0, 0, 3, 0, 0, 0, 0, 0]);

        expect(bars).toHaveLength(11);
        expect(bars[0]).toMatchObject({ total: 2, count: 1, share: 0.25 });
        expect(bars[5]).toMatchObject({ total: 7, count: 3, share: 0.75 });
        expect(bars[10]).toMatchObject({ total: 12, count: 0, share: 0 });
    });

    it('has empty bars before the first roll or without counts', () => {
        for (const counts of [[], undefined]) {
            const bars = rollBars(counts);
            expect(bars.every((bar) => bar.count === 0 && bar.share === 0)).toBe(true);
        }
    });

    it('scales to the highest bar or expectation', () => {
        expect(scaleOf(rollBars([]))).toBeCloseTo(1 / 6);
        expect(scaleOf(rollBars([0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 2]))).toBe(1);
    });

    it('rounds a share to a whole percent', () => {
        expect(percent(5 / 36)).toBe('14%');
        expect(percent(0)).toBe('0%');
    });
});
