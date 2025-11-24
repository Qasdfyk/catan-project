import type { HexCoords } from '../types/game';

// Size of a single hex (radius from center to vertex in pixels)
export const HEX_SIZE = 60;

// Canvas center (offset), to center the map on the screen
const CENTER_X = 400;
const CENTER_Y = 300;

/**
 * Converts Cube coordinates (q, r, s) to Pixels (x, y)
 * Layout: Pointy Top
 */
export const hexToPixel = (hex: HexCoords): { x: number; y: number } => {
    // Formula for Pointy Top Hexagons:
    // x = size * sqrt(3) * (q + r/2)
    // y = size * 3/2 * r
    
    const x = HEX_SIZE * Math.sqrt(3) * (hex.q + hex.r / 2);
    const y = HEX_SIZE * (3 / 2) * hex.r;

    // Add offset so (0,0,0) renders in the center of the canvas, not top-left
    return {
        x: x + CENTER_X,
        y: y + CENTER_Y
    };
};

/**
 * Returns the hex color string for a specific resource type.
 */
export const getResourceColor = (resource: string): string => {
    switch (resource) {
        case 'wood': return '#228B22';   // Forest Green
        case 'brick': return '#B22222';  // Fire Brick
        case 'sheep': return '#9ACD32';  // Yellow Green
        case 'wheat': return '#FFD700';  // Gold
        case 'ore': return '#708090';    // Slate Gray
        case 'desert': return '#F4A460'; // Sandy Brown
        default: return '#FFFFFF';
    }
};