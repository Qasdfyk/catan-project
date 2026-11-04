import { useEffect, useState } from 'react';
import { formatClock, isUrgent, secondsLeft } from '../utils/turnTimer';

const TICK_MS = 250;

interface TurnTimerProps {
    deadline: number;
    serverTime: number;
}

/** Counts from the moment it mounts, so it needs a new key for every state from the server. */
export const TurnTimer = ({ deadline, serverTime }: TurnTimerProps) => {
    const [left, setLeft] = useState(() => secondsLeft(deadline, serverTime, 0));

    useEffect(() => {
        const received = performance.now();
        const timer = window.setInterval(() => {
            setLeft(secondsLeft(deadline, serverTime, (performance.now() - received) / 1000));
        }, TICK_MS);
        return () => window.clearInterval(timer);
    }, [deadline, serverTime]);

    return (
        <span
            className={isUrgent(left) ? 'turn-timer urgent' : 'turn-timer'}
            title="Time left in this turn"
            data-testid="turn-timer"
        >{formatClock(left)}</span>
    );
};
