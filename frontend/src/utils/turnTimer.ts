/** From this many seconds left the countdown turns red. */
export const URGENT_SECONDS = 10;

/**
 * Whole seconds left in the turn. Both times come from the server's clock,
 * so a local clock that runs fast or slow doesn't change the result.
 */
export const secondsLeft = (deadline: number, serverTime: number, elapsedSeconds: number) =>
    Math.max(0, Math.ceil(deadline - serverTime - elapsedSeconds));

/** E.g. 42 -> "0:42", 125 -> "2:05". */
export const formatClock = (seconds: number) =>
    `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;

export const isUrgent = (seconds: number) => seconds <= URGENT_SECONDS;
