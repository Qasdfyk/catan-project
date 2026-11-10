import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { SideTabs } from './SideTabs';

// No DOM in the test setup: the tabs are rendered to markup and checked as text.
const render = (badge: number) => renderToStaticMarkup(
    <SideTabs
        tabs={[
            { id: 'log', label: 'Log', content: <p>the log</p> },
            { id: 'chat', label: 'Chat', badge, content: <p>the chat</p> },
        ]}
    />,
);

describe('SideTabs', () => {
    it('opens on the first tab and keeps the others mounted but hidden', () => {
        const markup = render(0);

        expect(markup).toMatch(/<button[^>]*aria-selected="true"[^>]*>Log<\/button>/);
        expect(markup).toMatch(/<div[^>]*id="tabpanel-log"[^>]*><p>the log<\/p>/);
        expect(markup).toMatch(/<div[^>]*id="tabpanel-chat"[^>]*hidden=""[^>]*><p>the chat<\/p>/);
    });

    it('shows a count of unread messages only when there are some', () => {
        expect(render(0)).not.toContain('tab-badge');
        expect(render(3)).toContain('<span class="tab-badge">3</span>');
    });
});
