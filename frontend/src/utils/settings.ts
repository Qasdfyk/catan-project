import type { DesertPlacement, GameSettings } from '../types/game';

export const STANDARD_SETTINGS: GameSettings = {
    victory_points: 10,
    discard_limit: 7,
    desert: 'random',
    friendly_robber: false,
    turn_seconds: null,
};

// A shorter game in which the leader can't be robbed back into the pack early.
export const TWO_PLAYER_SETTINGS: GameSettings = {
    victory_points: 8,
    discard_limit: 9,
    desert: 'random',
    friendly_robber: true,
    turn_seconds: null,
};

const range = (from: number, to: number) => Array.from({ length: to - from + 1 }, (_, index) => from + index);

export const VICTORY_POINT_OPTIONS = range(6, 15);
export const DISCARD_LIMIT_OPTIONS = range(5, 12);
export const TURN_SECONDS_OPTIONS = [null, 60, 90, 120, 180];

export const DESERT_LABELS: Record<DesertPlacement, string> = {
    random: 'Random',
    center: 'Centre',
};

export const turnTimerLabel = (seconds: number | null) => (seconds === null ? 'Off' : `${seconds} s`);

export const sameSettings = (a: GameSettings, b: GameSettings) =>
    a.victory_points === b.victory_points
    && a.discard_limit === b.discard_limit
    && a.desert === b.desert
    && a.friendly_robber === b.friendly_robber
    && a.turn_seconds === b.turn_seconds;

/** One line for the players, e.g. "First to 8 · Discard above 9 · Friendly robber". Standard choices are left out. */
export const settingsSummary = (settings: GameSettings) => {
    const parts = [`First to ${settings.victory_points}`, `Discard above ${settings.discard_limit}`];
    if (settings.desert === 'center') parts.push('Desert in the centre');
    if (settings.friendly_robber) parts.push('Friendly robber');
    if (settings.turn_seconds !== null) parts.push(`${settings.turn_seconds} s turns`);
    return parts.join(' · ');
};
