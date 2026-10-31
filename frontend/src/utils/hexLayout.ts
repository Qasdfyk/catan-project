import type { HexCoords, Position, TileResource } from '../types/game';

export const HEX_SIZE = 60;

export interface Point {
    x: number;
    y: number;
}

export const hexToPixel = (hex: HexCoords): Point => {
    // Pointy Top Layout Conversion
    const x = HEX_SIZE * Math.sqrt(3) * (hex.q + hex.r / 2);
    const y = HEX_SIZE * (3 / 2) * hex.r;
    return { x, y };
};

export const getVertexCoords = ({ hex, direction }: Position): Point => {
    const center = hexToPixel(hex);

    // BACKEND SYNC: Vertex 0 is "before" Edge 0.
    // Since Edge 0 is at 0 deg, Vertex 0 is at -30 deg.
    const angleRad = (Math.PI / 180) * (60 * direction - 30);

    return {
        x: center.x + HEX_SIZE * Math.cos(angleRad),
        y: center.y + HEX_SIZE * Math.sin(angleRad),
    };
};

/** BACKEND SYNC: Edge N runs from Vertex N to Vertex N+1 of the same hex. */
export const getEdgeEndpoints = ({ hex, direction }: Position): [Point, Point] => [
    getVertexCoords({ hex, direction }),
    getVertexCoords({ hex, direction: (direction + 1) % 6 }),
];

export const hexCorners = (hex: HexCoords): Point[] =>
    [0, 1, 2, 3, 4, 5].map((direction) => getVertexCoords({ hex, direction }));

export const samePosition = (a: Position, b: Position): boolean =>
    a.direction === b.direction && a.hex.q === b.hex.q && a.hex.r === b.hex.r;

/** How many of the 36 dice combinations produce this number. */
export const numberPips = (number: number): number => 6 - Math.abs(7 - number);

export const RESOURCE_COLORS: Record<TileResource, string> = {
    wood: '#2f7d4f',
    brick: '#b4532a',
    sheep: '#93c15a',
    wheat: '#e9bf3f',
    ore: '#7b8794',
    desert: '#dcc48e',
};
