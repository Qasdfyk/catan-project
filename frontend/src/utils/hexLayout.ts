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
 * Calculates the pixel coordinates and rotation for an edge.
 * Used for rendering Roads and Road Hitboxes.
 * * Direction 0: Top-Right (Between Vertex 0 and 1) -> Angle 0 degrees.
 * Direction 1: Right (Between Vertex 1 and 2) -> Angle 60 degrees.
 * ...
 */
export const getEdgeCoords = (hex: HexCoords, direction: number) => {
    const center = hexToPixel(hex);
    
    // In Pointy Top layout, the edges are at angles 0, 60, 120, 180, 240, 300 degrees
    // relative to the center.
    // Edge 0 is at 0 degrees (3 o'clock - Geometric, but verify visual layout).
    // Visual layout usually starts -30deg.
    // Edge 0 connects (-30) and (30). The midpoint is at 0 degrees.
    
    const angleDeg = direction * 60;
    const angleRad = (Math.PI / 180) * angleDeg;

    // Distance to edge midpoint is inner radius (sqrt(3)/2 * size)
    const innerRadius = (Math.sqrt(3) / 2) * HEX_SIZE;

    const x = center.x + innerRadius * Math.cos(angleRad);
    const y = center.y + innerRadius * Math.sin(angleRad);
    
    // Rotation of the road rectangle.
    // The edge at 0 degrees is a Vertical line? No.
    // Hex edge 0 (at 0 deg from center) is a Vertical line segment | ?
    // Let's trace vertices: V0(-30deg), V1(30deg).
    // The line connecting them is Vertical. Yes.
    // So the road rectangle needs to be rotated 90 degrees (PI/2) relative to the radius vector?
    // Radius vector is horizontal (0 deg). Road is vertical.
    // So rotation = angleRad + PI/2.
    
    return { 
        x, 
        y, 
        rotation: angleRad + (Math.PI / 2) 
    };
};

/**
 * Calculates the pixel coordinates for a vertex.
 * Used for rendering Settlements and Click Targets.
 */
export const getVertexCoords = (hex: HexCoords, direction: number) => {
    const center = hexToPixel(hex);
    
    // Pointy Top Vertices: 
    // i=0: -30 deg, i=1: 30 deg, i=2: 90 deg...
    const angleDeg = 60 * direction - 30;
    const angleRad = (Math.PI / 180) * angleDeg;
    
    return {
        x: center.x + HEX_SIZE * Math.cos(angleRad),
        y: center.y + HEX_SIZE * Math.sin(angleRad)
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