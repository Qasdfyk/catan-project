import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { RollStats } from './RollStats';

const COUNTS = [0, 1, 0, 0, 2, 4, 3, 0, 0, 0, 0];

// No DOM in the test setup: the panel is rendered to markup and checked as text.
const render = (counts: number[] | undefined, last: number | null) =>
    renderToStaticMarkup(<RollStats counts={counts} last={last} />);

const bar = (markup: string, total: number) =>
    markup.match(new RegExp(`<li[^>]*title="${total}: [^"]*"[^>]*>.*?</li>`))?.[0] ?? '';

describe('RollStats', () => {
    it('shows a bar with its count for every total', () => {
        const markup = render(COUNTS, 8);

        expect(markup.match(/class="roll-bar"/g)).toHaveLength(11);
        expect(bar(markup, 7)).toContain('<span class="roll-count">4</span>');
        expect(bar(markup, 2)).toContain('<span class="roll-count">0</span>');
        expect(markup).toContain('10 rolls');
    });

    it('highlights the last roll', () => {
        const markup = render(COUNTS, 8);

        expect(bar(markup, 8)).toContain('class="last"');
        expect(markup.match(/class="last"/g)).toHaveLength(1);
    });

    it('compares each total with the expected share', () => {
        expect(bar(render(COUNTS, 8), 6)).toContain('title="6: rolled 2 times (20%), expected 14%"');
    });

    it('starts empty before the first roll', () => {
        const markup = render(undefined, null);

        expect(markup).toContain('0 rolls');
        expect(markup).not.toContain('class="last"');
        expect(bar(markup, 7)).toContain('title="7: rolled 0 times, expected 17%"');
    });

    it('can be folded away', () => {
        expect(render(COUNTS, 8)).toContain('<details open="">');
    });
});
