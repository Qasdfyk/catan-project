// "Review this game": opens the analyzer of catan-analysis-engine in a new tab
// and hands it the record of the game that just ended.
//
// The analyzer is a static page on another origin (GitHub Pages), so the
// record goes by window.postMessage between the two tabs, never over the
// network or in a URL. The analyzer speaks first: a message sent before its
// page has loaded would be lost. The protocol is described in
// catan-analysis-engine's docs/web.md:
//
//   this tab:  window.open(analyzer + "#/replay?from=opener")
//   analyzer -> this tab: {type: "catan-review:ready", version: 1}
//   this tab -> analyzer: {type: "catan-review:record", version: 1, record, label, seat}
//                      or {type: "catan-review:error", version: 1, message}

/** The analyzer's page; VITE_REVIEW_URL points it at a local copy (http://localhost:5174/). */
export const REVIEW_URL: string = import.meta.env.VITE_REVIEW_URL ?? 'https://qasdfyk.github.io/catan-analysis-engine/';

const READY = 'catan-review:ready';
const VERSION = 1;
/** How long this tab answers the analyzer, e.g. after a reload of the analyzer. */
const LISTEN_MS = 30 * 60 * 1000;

/** The parts of `window` used here, so tests can pass a fake one. */
export interface ReviewWindow {
    open(url: string, target: string): Pick<Window, 'postMessage'> | null;
    addEventListener(type: 'message', listener: (e: MessageEvent) => void): void;
    removeEventListener(type: 'message', listener: (e: MessageEvent) => void): void;
    setTimeout(handler: () => void, ms: number): unknown;
}

/** The analyzer's address that waits for a record from this tab. */
export const reviewLink = (base = REVIEW_URL) => new URL('#/replay?from=opener', base).href;

/** What the analyzer is told besides the record. */
export interface ReviewOf {
    /** Shown under the board: "Game r1". */
    label: string;
    /** The seat of the player asking: the review is about their decisions. */
    seat: number;
}

/**
 * Opens the analyzer and sends it the record at `recordUrl` once it is ready.
 * Must run inside a click handler, or the browser blocks the new tab.
 * Returns false when it was blocked anyway.
 */
export function openReview(
    recordUrl: string,
    { label, seat }: ReviewOf,
    { base = REVIEW_URL, win = window as ReviewWindow, load = fetch as typeof fetch } = {},
): boolean {
    // Not "noopener": the analyzer needs window.opener to ask for the record.
    const viewer = win.open(reviewLink(base), '_blank');
    if (!viewer) return false;
    // Only the analyzer's origin may read the record: if the tab navigates
    // somewhere else, the browser drops the message instead of delivering it.
    const origin = new URL(base).origin;
    // Fetched once, while the analyzer loads.
    const record = load(recordUrl).then(async (response) => {
        if (!response.ok) throw new Error(`the server answered ${response.status}`);
        return response.text();
    });
    record.catch(() => {}); // answered when the analyzer asks

    const onMessage = (e: MessageEvent) => {
        if (e.source !== viewer || e.origin !== origin) return;
        const data = e.data as { type?: unknown; version?: unknown } | null;
        if (data?.type !== READY || data.version !== VERSION) return;
        record.then(
            (text) => viewer.postMessage({ type: 'catan-review:record', version: VERSION, record: text, label, seat }, origin),
            (error: Error) => viewer.postMessage({ type: 'catan-review:error', version: VERSION, message: error.message }, origin),
        );
    };
    win.addEventListener('message', onMessage);
    win.setTimeout(() => win.removeEventListener('message', onMessage), LISTEN_MS);
    return true;
}
