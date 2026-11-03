import { describe, expect, it } from 'vitest';
import { getEdgeEndpoints, getVertexCoords, hexToPixel, HEX_SIZE, numberPips } from './hexLayout';

const CENTER = { q: 0, r: 0, s: 0 };
const EAST = { q: 1, r: 0, s: -1 };

describe('hexLayout', () => {
    it('places the first neighbor to the east', () => {
        const { x, y } = hexToPixel(EAST);
        expect(x).toBeCloseTo(HEX_SIZE * Math.sqrt(3));
        expect(y).toBeCloseTo(0);
    });

    it('matches the vertex equivalence of the backend', () => {
        // Backend: Vertex(center, 0) is Vertex(east, 4) and Vertex(north-east, 2)
        const expected = getVertexCoords({ hex: CENTER, direction: 0 });
        const onEast = getVertexCoords({ hex: EAST, direction: 4 });
        const onNorthEast = getVertexCoords({ hex: { q: 1, r: -1, s: 0 }, direction: 2 });

        expect(onEast.x).toBeCloseTo(expected.x);
        expect(onEast.y).toBeCloseTo(expected.y);
        expect(onNorthEast.x).toBeCloseTo(expected.x);
        expect(onNorthEast.y).toBeCloseTo(expected.y);
    });

    it.each([0, 1, 2, 3, 4, 5])('draws edge %i along the side of the hex', (direction) => {
        // Regression: roads used to be drawn perpendicular to their edge
        const [from, to] = getEdgeEndpoints({ hex: CENTER, direction });
        const center = { x: (from.x + to.x) / 2, y: (from.y + to.y) / 2 };
        const radial = (Math.PI / 180) * direction * 60;
        const along = { x: to.x - from.x, y: to.y - from.y };

        expect(Math.hypot(along.x, along.y)).toBeCloseTo(HEX_SIZE);
        expect(along.x * Math.cos(radial) + along.y * Math.sin(radial)).toBeCloseTo(0);
        expect(center.x).toBeCloseTo((Math.sqrt(3) / 2) * HEX_SIZE * Math.cos(radial));
        expect(center.y).toBeCloseTo((Math.sqrt(3) / 2) * HEX_SIZE * Math.sin(radial));
    });

    it('counts probability pips of number tokens', () => {
        expect(numberPips(2)).toBe(1);
        expect(numberPips(6)).toBe(5);
        expect(numberPips(8)).toBe(5);
        expect(numberPips(12)).toBe(1);
    });
});
