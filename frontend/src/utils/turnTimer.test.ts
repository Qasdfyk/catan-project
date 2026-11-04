import { describe, expect, it } from 'vitest';
import { formatClock, isUrgent, secondsLeft } from './turnTimer';

describe('turn timer', () => {
    it('counts from the server time, not the local clock', () => {
        expect(secondsLeft(1_000_090, 1_000_000, 0)).toBe(90);
        expect(secondsLeft(1_000_090, 1_000_000, 30)).toBe(60);
    });

    it('rounds a part of a second up', () => {
        expect(secondsLeft(1_000_042.4, 1_000_000, 0)).toBe(43);
        expect(secondsLeft(1_000_010, 1_000_000.75, 0.5)).toBe(9);
    });

    it('never goes below zero', () => {
        expect(secondsLeft(1_000_005, 1_000_000, 8)).toBe(0);
    });

    it('formats minutes and seconds', () => {
        expect(formatClock(42)).toBe('0:42');
        expect(formatClock(125)).toBe('2:05');
        expect(formatClock(0)).toBe('0:00');
    });

    it('is urgent in the last ten seconds', () => {
        expect(isUrgent(11)).toBe(false);
        expect(isUrgent(10)).toBe(true);
        expect(isUrgent(0)).toBe(true);
    });
});
