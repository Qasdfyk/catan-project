/**
 * The host's rematch request is still waiting for an answer while the error
 * on screen is the one there was when it was sent. A refusal shows a new
 * error, and an old one fading away also ends the wait, so the button never
 * stays stuck.
 */
export const awaitingRematch = (errorWhenRequested: string | null | undefined, error: string | null) =>
    errorWhenRequested !== undefined && error === errorWhenRequested;
