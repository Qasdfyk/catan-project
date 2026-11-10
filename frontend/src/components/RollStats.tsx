import { useState } from 'react';
import { percent, rollBars, scaleOf } from '../utils/rollStats';

interface RollStatsProps {
    /** How often each total was rolled, index 0 being the 2s. */
    counts: number[] | undefined;
    /** The total of the last roll, highlighted; null before the first roll. */
    last: number | null;
    /** Inside a tab of the side panel: always open, the tab names it. */
    inTab?: boolean;
}

/** A small histogram of the totals rolled so far, next to how often each comes up on average. */
export const RollStats = ({ counts, last, inTab = false }: RollStatsProps) => {
    const [open, setOpen] = useState(true);
    const bars = rollBars(counts);
    const rolls = bars.reduce((sum, bar) => sum + bar.count, 0);
    const scale = scaleOf(bars);
    const height = (share: number) => `${(share / scale) * 100}%`;

    const chart = (
            <>
            <ol className="roll-bars">
                {bars.map((bar) => (
                    <li
                        key={bar.total}
                        className={bar.total === last ? 'last' : undefined}
                        title={`${bar.total}: rolled ${bar.count} ${bar.count === 1 ? 'time' : 'times'}`
                            + (rolls > 0 ? ` (${percent(bar.share)})` : '')
                            + `, expected ${percent(bar.expected)}`}
                    >
                        <span className="roll-count">{bar.count}</span>
                        <span className="roll-track">
                            <span className="roll-bar" style={{ height: height(bar.share) }} />
                            <span className="roll-expected" style={{ bottom: height(bar.expected) }} />
                        </span>
                        <span className="roll-number">{bar.total}</span>
                    </li>
                ))}
            </ol>
            <p className="muted hint">The line shows the expected share, from 36 dice combinations.</p>
            </>
    );
    const total = <span className="muted" data-testid="roll-total">{rolls} {rolls === 1 ? 'roll' : 'rolls'}</span>;

    if (inTab) {
        return (
            <section className="roll-stats" aria-label="Dice rolls">
                <p className="roll-summary">{total}</p>
                {chart}
            </section>
        );
    }
    return (
        <section className="panel roll-stats" aria-label="Dice rolls">
            <details open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
                <summary>
                    <h2>Dice rolls</h2>
                    {total}
                </summary>
                {chart}
            </details>
        </section>
    );
};
