import { memo } from 'react';
import type { BoardTile, GameView, HexCoords, Player, PlayerColor, Port, Position, Resource, TileResource } from '../types/game';
import { ArtDefs, ResourceIconArt, TileArt } from './Art';
import { hexKey, type BuiltChanges } from '../utils/changes';
import {
    getEdgeEndpoints,
    getVertexCoords,
    hexCorners,
    hexToPixel,
    HEX_SIZE,
    numberPips,
    RESOURCE_COLORS,
    type Point,
} from '../utils/hexLayout';
import { PLAYER_COLORS } from '../utils/labels';
import './board.css';

const BOARD_EXTENT = HEX_SIZE * 5.3;
const VIEW_BOX = `${-BOARD_EXTENT} ${-BOARD_EXTENT} ${BOARD_EXTENT * 2} ${BOARD_EXTENT * 2}`;

export interface BoardTargets {
    settlements: Position[];
    roads: Position[];
    cities: Position[];
    robberHexes: HexCoords[];
}

interface BoardProps {
    game: GameView;
    players: Player[];
    targets: BoardTargets;
    onSettlement: (position: Position) => void;
    onRoad: (position: Position) => void;
    onCity: (position: Position) => void;
    onRobber: (hex: HexCoords) => void;
    /** Tiles that just produced; without it every tile with the rolled number is marked. */
    producing?: HexCoords[];
    /** The pieces built last and the robber's new tile, marked with a ring. */
    recent?: BuiltChanges;
}

const points = (corners: Point[]) => corners.map(({ x, y }) => `${x},${y}`).join(' ');

const positionKey = (kind: string, { hex, direction }: Position) =>
    `${kind}-${hex.q}-${hex.r}-${direction}`;

const positionLabel = (kind: string, { hex, direction }: Position) =>
    `${kind} ${hex.q},${hex.r},${direction}`;

interface TileProps {
    q: number;
    r: number;
    s: number;
    resource: TileResource;
    number: number | null;
    rolled: boolean;
}

// Props are plain values, so a tile re-renders only when it really changes.
const Tile = memo(({ q, r, s, resource, number, rolled }: TileProps) => {
    const hex = { q, r, s };
    const center = hexToPixel(hex);
    const hot = number === 6 || number === 8;
    const radius = HEX_SIZE * 0.33;
    return (
        <g data-tile={hexKey(hex)}>
            <polygon
                className={rolled ? 'tile rolled' : 'tile'}
                points={points(hexCorners(hex))}
                fill={`url(#art-ground-${resource})`}
            />
            <TileArt resource={resource} x={center.x} y={center.y} rolled={rolled} />
            {number !== null && (
                <g className={hot ? 'token hot' : 'token'}>
                    <circle className="token-shadow" cx={center.x + 1.2} cy={center.y + 2.4} r={radius} />
                    <circle className="token-disc" cx={center.x} cy={center.y} r={radius} />
                    <circle className="token-ring" cx={center.x} cy={center.y} r={radius - 3.5} />
                    <text x={center.x} y={center.y - 3}>{number}</text>
                    <text className="pips" x={center.x} y={center.y + 11}>
                        {'•'.repeat(numberPips(number))}
                    </text>
                </g>
            )}
        </g>
    );
});

/** Sand and shallow water around the island: each tile's hex, grown, under all tiles. */
const Coast = memo(({ layout }: { layout: string }) => {
    const hexes = layout.split('|').map((key) => {
        const [q, r] = key.split(',').map(Number);
        return { q, r, s: -q - r };
    });
    const grown = (hex: HexCoords, scale: number) => {
        const center = hexToPixel(hex);
        return points(hexCorners(hex).map(({ x, y }) => ({
            x: center.x + (x - center.x) * scale,
            y: center.y + (y - center.y) * scale,
        })));
    };
    return (
        <g className="coast" aria-hidden="true">
            <g opacity={0.45}>
                {hexes.map((hex) => <polygon key={hexKey(hex)} className="coast-shallow" points={grown(hex, 1.12)} />)}
            </g>
            {hexes.map((hex) => <polygon key={hexKey(hex)} className="coast-sand" points={grown(hex, 1.09)} />)}
        </g>
    );
});

const PortMark = ({ port }: { port: Port }) => {
    const [first, second] = port.vertices.map(getVertexCoords);
    const middle = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
    const reach = Math.hypot(middle.x, middle.y);
    const outward = (HEX_SIZE * 0.72 + reach) / reach;
    const anchor = { x: middle.x * outward, y: middle.y * outward };
    const generic = port.type === '3:1';
    const resource = port.type.split('_')[0] as keyof typeof RESOURCE_COLORS;

    const radius = HEX_SIZE * 0.34;
    const icon = radius * 1.15;

    return (
        <g className="port" data-port={port.type}>
            <title>{generic ? 'Any resource 3:1' : `${resource} 2:1`}</title>
            <line x1={anchor.x} y1={anchor.y} x2={first.x} y2={first.y} />
            <line x1={anchor.x} y1={anchor.y} x2={second.x} y2={second.y} />
            <circle className="port-shadow" cx={anchor.x + 1.2} cy={anchor.y + 2.4} r={radius} />
            <circle
                className="port-disc"
                cx={anchor.x}
                cy={anchor.y}
                r={radius}
                style={{ stroke: generic ? '#8a7a5c' : RESOURCE_COLORS[resource] }}
            />
            {generic ? (
                <text className="port-generic" x={anchor.x} y={anchor.y}>3:1</text>
            ) : (
                <>
                    <svg
                        x={anchor.x - icon / 2}
                        y={anchor.y - radius + 2}
                        width={icon}
                        height={icon}
                        viewBox="0 0 32 32"
                        aria-hidden="true"
                    >
                        <ResourceIconArt resource={resource as Resource} />
                    </svg>
                    <text className="port-ratio" x={anchor.x} y={anchor.y + radius * 0.58}>2:1</text>
                </>
            )}
        </g>
    );
};

const Settlement = ({ at, color }: { at: Point; color: string }) => (
    <polygon
        className="piece"
        fill={color}
        points={points([
            { x: at.x - 11, y: at.y + 9 },
            { x: at.x - 11, y: at.y - 3 },
            { x: at.x, y: at.y - 13 },
            { x: at.x + 11, y: at.y - 3 },
            { x: at.x + 11, y: at.y + 9 },
        ])}
    />
);

const City = ({ at, color }: { at: Point; color: string }) => (
    <polygon
        className="piece"
        fill={color}
        points={points([
            { x: at.x - 16, y: at.y + 11 },
            { x: at.x - 16, y: at.y - 5 },
            { x: at.x - 7, y: at.y - 15 },
            { x: at.x + 2, y: at.y - 5 },
            { x: at.x + 2, y: at.y - 1 },
            { x: at.x + 16, y: at.y - 1 },
            { x: at.x + 16, y: at.y + 11 },
        ])}
    />
);

const Robber = ({ hex }: { hex: HexCoords }) => {
    const center = hexToPixel(hex);
    return (
        <g className="robber" transform={`translate(${center.x + HEX_SIZE * 0.45} ${center.y - HEX_SIZE * 0.35})`}>
            <title>Robber</title>
            <circle cx={0} cy={-13} r={8} />
            <path d="M -10 15 Q -11 -8 0 -8 Q 11 -8 10 15 Z" />
        </g>
    );
};

// Marks of what changed last; they never catch a click meant for a target.
// The glow of a road lies under the roads, so the road keeps its color.
const RecentRoads = ({ recent }: { recent: BuiltChanges }) => (
    <g className="recent" aria-hidden="true">
        {recent.roads.map((road) => {
            const [from, to] = getEdgeEndpoints(road);
            return (
                <line
                    key={positionKey('recent-road', road)}
                    className="recent-road"
                    data-recent="road"
                    x1={from.x}
                    y1={from.y}
                    x2={to.x}
                    y2={to.y}
                />
            );
        })}
    </g>
);

const RecentMarks = ({ recent }: { recent: BuiltChanges }) => (
    <g className="recent" aria-hidden="true">
        {recent.robber && (
            <polygon className="recent-hex" data-recent="robber" points={points(hexCorners(recent.robber))} />
        )}
        {[...recent.settlements, ...recent.cities].map((building) => {
            const at = getVertexCoords(building);
            return (
                <circle
                    key={positionKey('recent-building', building)}
                    className="recent-ring"
                    data-recent={building.type}
                    cx={at.x}
                    cy={at.y}
                    r={building.type === 'city' ? 24 : 19}
                />
            );
        })}
    </g>
);

export const Board = ({
    game,
    players,
    targets,
    onSettlement,
    onRoad,
    onCity,
    onRobber,
    producing,
    recent,
}: BoardProps) => {
    const nameOf = (color: PlayerColor) => players.find((p) => p.color === color)?.name ?? color;
    const producingKeys = producing && new Set(producing.map(hexKey));
    const isRolled = (tile: BoardTile) => (producingKeys
        ? producingKeys.has(hexKey(tile.hex))
        : game.dice_roll !== null && tile.number === game.dice_roll);

    return (
        <svg className="board" viewBox={VIEW_BOX} role="img" aria-label="Game board">
            <ArtDefs />
            <Coast layout={game.board_tiles.map((tile) => hexKey(tile.hex)).join('|')} />

            {game.board_tiles.map((tile) => (
                <Tile
                    key={`${tile.hex.q}-${tile.hex.r}`}
                    q={tile.hex.q}
                    r={tile.hex.r}
                    s={tile.hex.s}
                    resource={tile.resource}
                    number={tile.number}
                    rolled={isRolled(tile)}
                />
            ))}

            {/* Above all tiles, so a neighbour never covers the outline */}
            {game.board_tiles.filter(isRolled).map((tile) => (
                <polygon
                    key={`rolled-${hexKey(tile.hex)}`}
                    className="rolled-outline"
                    points={points(hexCorners(tile.hex))}
                />
            ))}

            {game.ports.map((port) => (
                <PortMark key={positionKey('port', port.vertices[0])} port={port} />
            ))}

            {game.robber_hex && <Robber hex={game.robber_hex} />}

            {targets.robberHexes.map((hex) => (
                <polygon
                    key={`robber-${hex.q}-${hex.r}`}
                    className="target target-hex"
                    data-target={`robber ${hex.q},${hex.r}`}
                    points={points(hexCorners(hex))}
                    onClick={() => onRobber(hex)}
                />
            ))}

            {recent && <RecentRoads recent={recent} />}

            {game.roads.map((road) => {
                const [from, to] = getEdgeEndpoints(road);
                return (
                    <g key={positionKey('road', road)} data-road={road.color}>
                        <title>Road of {nameOf(road.color)}</title>
                        <line className="road-outline" x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
                        <line
                            className="road"
                            stroke={PLAYER_COLORS[road.color]}
                            x1={from.x}
                            y1={from.y}
                            x2={to.x}
                            y2={to.y}
                        />
                    </g>
                );
            })}

            {targets.roads.map((road) => {
                const [from, to] = getEdgeEndpoints(road);
                return (
                    <g
                        key={positionKey('target-road', road)}
                        className="target target-road"
                        data-target={positionLabel('road', road)}
                        onClick={() => onRoad(road)}
                    >
                        <line className="target-road-mark" x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
                        <line className="target-road-hit" x1={from.x} y1={from.y} x2={to.x} y2={to.y} />
                    </g>
                );
            })}

            {game.settlements.map((building) => {
                const at = getVertexCoords(building);
                const Piece = building.type === 'city' ? City : Settlement;
                return (
                    <g key={positionKey('building', building)} data-building={building.type}>
                        <title>{building.type} of {nameOf(building.owner)}</title>
                        <Piece at={at} color={PLAYER_COLORS[building.owner]} />
                    </g>
                );
            })}

            {recent && <RecentMarks recent={recent} />}

            {targets.settlements.map((position) => {
                const at = getVertexCoords(position);
                return (
                    <circle
                        key={positionKey('target-settlement', position)}
                        className="target target-vertex"
                        data-target={positionLabel('settlement', position)}
                        cx={at.x}
                        cy={at.y}
                        r={13}
                        onClick={() => onSettlement(position)}
                    />
                );
            })}

            {targets.cities.map((position) => {
                const at = getVertexCoords(position);
                return (
                    <circle
                        key={positionKey('target-city', position)}
                        className="target target-vertex"
                        data-target={positionLabel('city', position)}
                        cx={at.x}
                        cy={at.y}
                        r={22}
                        onClick={() => onCity(position)}
                    />
                );
            })}
        </svg>
    );
};
