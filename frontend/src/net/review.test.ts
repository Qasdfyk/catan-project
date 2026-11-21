import { describe, expect, it } from 'vitest';
import { openReview, reviewLink, type ReviewWindow } from './review';

const BASE = 'https://example.github.io/analyzer/';
const ORIGIN = 'https://example.github.io';
const READY = { type: 'catan-review:ready', version: 1 };

// A fake window: what the code opened, and the messages it sent there.
const setup = (respond: () => Promise<Response> = async () => new Response('{"format":"catan-game-record"}')) => {
    const posted: { message: unknown; origin: string }[] = [];
    const listeners: ((e: MessageEvent) => void)[] = [];
    const opened: string[] = [];
    const viewer = { postMessage: (message: unknown, origin: string) => posted.push({ message, origin }) };
    const fetched: string[] = [];
    const win: ReviewWindow = {
        open: (url) => {
            opened.push(url);
            return viewer as unknown as Window;
        },
        addEventListener: (_, l) => listeners.push(l),
        removeEventListener: (_, l) => listeners.splice(listeners.indexOf(l), 1),
        setTimeout: () => 0,
    };
    const load = (async (url: string) => {
        fetched.push(url);
        return respond();
    }) as typeof fetch;
    const send = async (data: unknown, source: unknown = viewer, origin = ORIGIN) => {
        listeners.forEach((l) => l({ data, source, origin } as MessageEvent));
        await new Promise((resolve) => setTimeout(resolve, 0));
    };
    return { win, load, opened, posted, fetched, send, listeners };
};

describe('openReview', () => {
    it('opens the analyzer at the page that waits for a record', () => {
        expect(reviewLink(BASE)).toBe('https://example.github.io/analyzer/#/replay?from=opener');
        expect(reviewLink('http://localhost:5174/')).toBe('http://localhost:5174/#/replay?from=opener');
    });

    it('sends the record when the analyzer says it is ready, to its origin only', async () => {
        const { win, load, opened, posted, fetched, send } = setup();
        expect(openReview('/api/rooms/r1/record', { label: 'Game r1', seat: 2 }, { base: BASE, win, load })).toBe(true);
        expect(opened).toEqual([reviewLink(BASE)]);
        expect(fetched).toEqual(['/api/rooms/r1/record']);
        expect(posted).toEqual([]); // nothing before "ready"

        await send(READY);
        expect(posted).toEqual([{
            message: { type: 'catan-review:record', version: 1, record: '{"format":"catan-game-record"}', label: 'Game r1', seat: 2 },
            origin: ORIGIN,
        }]);

        // A reload of the analyzer asks again and gets the same record, fetched once
        await send(READY);
        expect(posted).toHaveLength(2);
        expect(fetched).toHaveLength(1);
    });

    it('ignores other windows, other origins and other messages', async () => {
        const { win, load, posted, send } = setup();
        openReview('/api/rooms/r1/record', { label: 'Game r1', seat: 2 }, { base: BASE, win, load });
        await send(READY, { postMessage() {} });
        await send(READY, undefined, 'https://evil.example');
        await send({ type: 'catan-review:ready', version: 2 });
        await send('catan-review:ready');
        expect(posted).toEqual([]);
    });

    it('tells the analyzer when the record cannot be fetched', async () => {
        const { win, load, posted, send } = setup(async () => new Response('', { status: 409 }));
        openReview('/api/rooms/r1/record', { label: 'Game r1', seat: 2 }, { base: BASE, win, load });
        await send(READY);
        expect(posted[0].message).toEqual({ type: 'catan-review:error', version: 1, message: 'the server answered 409' });
    });

    it('reports a blocked tab', () => {
        const { win, load, fetched, listeners } = setup();
        win.open = () => null;
        expect(openReview('/api/rooms/r1/record', { label: 'Game r1', seat: 2 }, { base: BASE, win, load })).toBe(false);
        expect(fetched).toEqual([]);
        expect(listeners).toEqual([]);
    });
});
