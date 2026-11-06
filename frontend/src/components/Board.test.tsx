import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { Board, type BoardTargets } from './Board';
import { Dice } from './Dice';
import { NO_BUILT, type BuiltChanges } from '../utils/changes';
import type { Building, GameView, HexCoords } from '../types/game';

const CENTER = { q: 0, r: 0, s: 0 };
const EAST = { q: 1, r: 0, s: -1 };

const NO_TARGETS: BoardTargets = { settlements: [], roads: [], cities: [], robberHexes: [] };

const SETTLEMENT: Building = { hex: CENTER, direction: 0, owner: 'red', type: 'settlement' };

const GAME = {
    dice_roll: 8,
    dice: [4, 4],
    robber_hex: EAST,
    board_tiles: [
        { hex: CENTER, resource: 'wood', number: 8 },
        { hex: EAST, resource: 'ore', number: 8 },
    ],
    ports: [],
    roads: [{ hex: CENTER, direction: 1, color: 'red' }],
    settlements: [SETTLEMENT],
} as unknown as GameView;

const render = (producing?: HexCoords[], recent?: BuiltChanges) => renderToStaticMarkup(
    <Board
        game={GAME}
        players={[]}
        targets={NO_TARGETS}
        onSettlement={() => {}}
        onRoad={() => {}}
        onCity={() => {}}
        onRobber={() => {}}
        producing={producing}
        recent={recent}
    />,
);

const tileClass = (markup: string, hex: HexCoords) =>
    markup.match(new RegExp(`data-tile="${hex.q},${hex.r}"><polygon class="([^"]+)"`))?.[1];

describe('Board feedback', () => {
    it('marks every tile with the rolled number without a list of producing tiles', () => {
        const markup = render();
        expect(tileClass(markup, CENTER)).toBe('tile rolled');
        expect(tileClass(markup, EAST)).toBe('tile rolled');
    });

    it('marks only the producing tiles when given', () => {
        const markup = render([CENTER]);
        expect(tileClass(markup, CENTER)).toBe('tile rolled');
        expect(tileClass(markup, EAST)).toBe('tile');
        expect(tileClass(render([]), CENTER)).toBe('tile');
    });

    it('rings the pieces built last and the robber tile', () => {
        const markup = render([], {
            roads: GAME.roads,
            settlements: [SETTLEMENT],
            cities: [],
            robber: EAST,
        });
        expect(markup).toContain('data-recent="road"');
        expect(markup).toContain('data-recent="settlement"');
        expect(markup).toContain('data-recent="robber"');
    });

    it('rings nothing when nothing changed', () => {
        expect(render([], NO_BUILT)).not.toContain('data-recent');
        expect(render()).not.toContain('data-recent');
    });
});

describe('Dice', () => {
    it('tumbles only right after a roll', () => {
        expect(renderToStaticMarkup(<Dice values={[3, 4]} total={7} rolling />)).toContain('class="dice rolling"');
        expect(renderToStaticMarkup(<Dice values={[3, 4]} total={7} />)).toContain('class="dice"');
    });
});
