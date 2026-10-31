import type { PlayerColor, Resource } from '../types/game';

export const RESOURCE_LABELS: Record<Resource, string> = {
    wood: 'Wood',
    brick: 'Brick',
    sheep: 'Sheep',
    wheat: 'Wheat',
    ore: 'Ore',
};

export const PLAYER_COLORS: Record<PlayerColor, string> = {
    red: '#d33a2c',
    blue: '#2f6fd0',
    white: '#f4f1e8',
    orange: '#ee8a1d',
};
