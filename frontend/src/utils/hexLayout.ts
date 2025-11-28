import type { HexCoords } from '../types/game';

export const HEX_SIZE = 45;
const CENTER_X = 400;
const CENTER_Y = 300;

export const hexToPixel = (hex: HexCoords): { x: number; y: number } => {
    // Pointy Top Layout Conversion
    const x = HEX_SIZE * Math.sqrt(3) * (hex.q + hex.r / 2);
    const y = HEX_SIZE * (3 / 2) * hex.r;
    return { x: x + CENTER_X, y: y + CENTER_Y };
};

export const getEdgeCoords = (hex: HexCoords, direction: number) => {
    const center = hexToPixel(hex);
    
    // BACKEND SYNC: Direction 0 = EAST (0 degrees).
    // Direction increases clockwise by 60 deg.
    const angleDeg = direction * 60; 
    const angleRad = (Math.PI / 180) * angleDeg;

    const innerRadius = (Math.sqrt(3) / 2) * HEX_SIZE;
    
    const x = center.x + innerRadius * Math.cos(angleRad);
    const y = center.y + innerRadius * Math.sin(angleRad);
    
    return { x, y, rotation: angleRad + (Math.PI / 2) };
};

export const getVertexCoords = (hex: HexCoords, direction: number) => {
    const center = hexToPixel(hex);
    
    // BACKEND SYNC: Vertex 0 is "before" Edge 0.
    // Since Edge 0 is at 0 deg, Vertex 0 is at -30 deg.
    const angleDeg = 60 * direction - 30;
    const angleRad = (Math.PI / 180) * angleDeg;
    
    return {
        x: center.x + HEX_SIZE * Math.cos(angleRad),
        y: center.y + HEX_SIZE * Math.sin(angleRad)
    };
};

export const getResourceColor = (resource: string): string => {
    switch (resource) {
        case 'wood': return '#228B22';
        case 'brick': return '#B22222';
        case 'sheep': return '#9ACD32';
        case 'wheat': return '#FFD700';
        case 'ore': return '#708090';
        case 'desert': return '#F4A460';
        default: return '#FFFFFF';
    }
};