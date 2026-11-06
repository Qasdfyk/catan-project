import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { CardGainBadge, RollGains } from './RollGains';

// No DOM in the test setup: the pieces are rendered to markup and checked as text.
const text = (markup: string) => markup.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();

describe('RollGains', () => {
    it('lists the gains in the order of the hand', () => {
        const markup = renderToStaticMarkup(<RollGains gains={{ ore: 2, wood: 1 }} />);
        expect(text(markup)).toBe('+1 Wood +2 Ore');
        expect(markup).toContain('role="status"');
    });

    it('shows nothing without gains', () => {
        expect(renderToStaticMarkup(<RollGains gains={{}} />)).toBe('');
        expect(renderToStaticMarkup(<RollGains gains={{ wheat: 0 }} />)).toBe('');
    });
});

describe('CardGainBadge', () => {
    it('shows how many cards a player got', () => {
        const markup = renderToStaticMarkup(<CardGainBadge gain={2} />);
        expect(markup).toContain('class="gain-badge"');
        expect(markup).toContain('title="Got 2 cards from the roll"');
        expect(text(markup)).toBe('+2');
    });

    it('shows nothing for no gain', () => {
        expect(renderToStaticMarkup(<CardGainBadge gain={undefined} />)).toBe('');
        expect(renderToStaticMarkup(<CardGainBadge gain={0} />)).toBe('');
    });
});
