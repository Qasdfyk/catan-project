import type { Cards, DevCard, PlayerColor, Resource } from '../types/game';

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

export const DEV_CARD_LABELS: Record<DevCard, string> = {
    knight: 'Knight',
    victory_point: 'Victory Point',
    road_building: 'Road Building',
    year_of_plenty: 'Year of Plenty',
    monopoly: 'Monopoly',
};

export const DEV_CARD_HELP: Record<DevCard, string> = {
    knight: 'Move the robber and steal a card.',
    victory_point: 'Worth 1 point. Hidden until it wins you the game.',
    road_building: 'Build 2 roads for free.',
    year_of_plenty: 'Take any 2 cards from the bank.',
    monopoly: 'Take all cards of one resource from everyone.',
};

export const countCards = (cards: Cards) =>
    Object.values(cards).reduce((sum, amount) => sum + (amount ?? 0), 0);
