/** The totals two dice can show. */
export const DICE_TOTALS = [2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];

/** Of the 36 ways two dice can land, how many give this total: 1 for a 2, 6 for a 7. */
export const combinations = (total: number) => 6 - Math.abs(7 - total);

/** The share of rolls a total gets on average, e.g. 1/6 for a 7. */
export const expectedShare = (total: number) => combinations(total) / 36;

export interface RollBar {
    total: number;
    count: number;
    /** Share of all rolls so far; 0 before the first roll. */
    share: number;
    expected: number;
}

/** One bar per total, from the counts the server sends (index 0 is the 2s); missing counts are zero. */
export const rollBars = (counts: readonly number[] | undefined): RollBar[] => {
    const rolls = DICE_TOTALS.map((_, index) => counts?.[index] ?? 0);
    const sum = rolls.reduce((total, count) => total + count, 0);
    return DICE_TOTALS.map((total, index) => ({
        total,
        count: rolls[index],
        share: sum === 0 ? 0 : rolls[index] / sum,
        expected: expectedShare(total),
    }));
};

/** The largest share among the bars and their expectations, so both fit the same scale. */
export const scaleOf = (bars: RollBar[]) =>
    Math.max(...bars.map((bar) => Math.max(bar.share, bar.expected)));

/** E.g. 0.1389 -> "14%". */
export const percent = (share: number) => `${Math.round(share * 100)}%`;
