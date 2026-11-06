import { describe, expect, it } from 'vitest';
import { awaitingRematch } from './rematch';

describe('rematch request', () => {
    it('is not waiting before the host asks', () => {
        expect(awaitingRematch(undefined, null)).toBe(false);
        expect(awaitingRematch(undefined, 'Only the host can start a rematch.')).toBe(false);
    });

    it('waits until the server answers', () => {
        expect(awaitingRematch(null, null)).toBe(true);
        expect(awaitingRematch('Not connected. Reconnecting…', 'Not connected. Reconnecting…')).toBe(true);
    });

    it('stops waiting when the server refuses', () => {
        expect(awaitingRematch(null, 'The game is not over.')).toBe(false);
    });

    it('stops waiting when an earlier error goes away', () => {
        expect(awaitingRematch('The game is not over.', null)).toBe(false);
    });
});
