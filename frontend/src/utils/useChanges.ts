import { useEffect, useState } from 'react';
import type { Cards, PublicState } from '../types/game';
import { diffStates, isEmptyBuilt, NO_BUILT, type BuiltChanges, type RollChanges } from './changes';

/** How long the feedback of a roll stays: the producing tiles and the gains. */
export const ROLL_VISIBLE_MS = 2600;

export interface Changes {
    /** The last roll while its feedback shows, null once it faded. */
    roll: RollChanges | null;
    /** Counts the rolls seen, to restart the dice animation on every one. */
    rollCount: number;
    /** The last pieces built and the robber's last move, kept until something else happens. */
    built: BuiltChanges;
}

interface Seen {
    state: PublicState;
    resources: Cards;
}

/** Compares every new state with the one before it and keeps what changed. */
export const useChanges = (state: PublicState, resources: Cards): Changes => {
    const [seen, setSeen] = useState<Seen>({ state, resources });
    const [roll, setRoll] = useState<RollChanges | null>(null);
    const [rollCount, setRollCount] = useState(0);
    const [built, setBuilt] = useState<BuiltChanges>(NO_BUILT);

    // Derived while rendering, so the feedback shows in the same frame as the new state
    if (seen.state !== state) {
        const changes = diffStates(seen.state, state, seen.resources, resources);
        const turnPassed = seen.state.game?.current_seat !== state.game?.current_seat;
        setSeen({ state, resources });
        if (changes.roll) {
            setRoll(changes.roll);
            setRollCount(rollCount + 1);
        }
        if (changes.roll || turnPassed || !isEmptyBuilt(changes.built)) setBuilt(changes.built);
    }

    useEffect(() => {
        if (roll === null) return;
        const timer = window.setTimeout(() => setRoll(null), ROLL_VISIBLE_MS);
        return () => window.clearTimeout(timer);
    }, [roll]);

    return { roll, rollCount, built };
};
