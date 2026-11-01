import type { BoardTile, GameView, HexCoords, Player, PlayerColor, Port, Position, TileResource } from '../types/game';
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
}

const points = (corners: Point[]) => corners.map(({ x, y }) => `${x},${y}`).join(' ');

const positionKey = (kind: string, { hex, direction }: Position) =>
    `${kind}-${hex.q}-${hex.r}-${direction}`;

const positionLabel = (kind: string, { hex, direction }: Position) =>
    `${kind} ${hex.q},${hex.r},${direction}`;

// Scenery around the number token, kept to simple shapes in tile coordinates.
const SCENERY_SPOTS = [[-30, -30], [28, -32], [-34, 22], [32, 24], [0, 40], [0, -42]];

const TileScenery = ({ resource }: { resource: TileResource }) => (
    <g className={`scenery scenery-${resource}`}>
        {SCENERY_SPOTS.map(([x, y]) => {
            const key = `${x}-${y}`;
            switch (resource) {
                case 'wood':
                    return <path key={key} d={`M ${x} ${y - 11} l 8 15 h -5 v 5 h -6 v -5 h -5 z`} />;
                case 'brick':
                    return <path key={key} d={`M ${x - 9} ${y - 4} h 18 v 8 h -18 z M ${x - 9} ${y} h 18 M ${x} ${y - 4} v 4`} />;
                case 'sheep':
                    return <ellipse key={key} cx={x} cy={y} rx={8} ry={5.5} />;
                case 'wheat':
                    return <path key={key} d={`M ${x} ${y + 10} V ${y - 10} M ${x} ${y - 7} l -5 -3 M ${x} ${y - 7} l 5 -3 M ${x} ${y - 1} l -5 -3 M ${x} ${y - 1} l 5 -3`} />;
                case 'ore':
                    return <path key={key} d={`M ${x - 12} ${y + 8} L ${x - 3} ${y - 9} L ${x + 2} ${y - 1} L ${x + 5} ${y - 5} L ${x + 12} ${y + 8} Z`} />;
                default:
                    return <circle key={key} cx={x} cy={y} r={2.5} />;
            }
        })}
    </g>
);

const Tile = ({ tile, rolled }: { tile: BoardTile; rolled: boolean }) => {
    const center = hexToPixel(tile.hex);
    const hot = tile.number === 6 || tile.number === 8;
    return (
        <g>
            <polygon
                className={rolled ? 'tile rolled' : 'tile'}
                points={points(hexCorners(tile.hex))}
                fill={RESOURCE_COLORS[tile.resource]}
            />
            <g transform={`translate(${center.x} ${center.y})`}>
                <TileScenery resource={tile.resource} />
            </g>
            {tile.number !== null && (
                <g className={hot ? 'token hot' : 'token'}>
                    <circle cx={center.x} cy={center.y} r={HEX_SIZE * 0.33} />
                    <text x={center.x} y={center.y - 3}>{tile.number}</text>
                    <text className="pips" x={center.x} y={center.y + 11}>
                        {'•'.repeat(numberPips(tile.number))}
                    </text>
                </g>
            )}
        </g>
    );
};

const PortMark = ({ port }: { port: Port }) => {
    const [first, second] = port.vertices.map(getVertexCoords);
    const middle = { x: (first.x + second.x) / 2, y: (first.y + second.y) / 2 };
    const reach = Math.hypot(middle.x, middle.y);
    const outward = (HEX_SIZE * 0.72 + reach) / reach;
    const anchor = { x: middle.x * outward, y: middle.y * outward };
    const generic = port.type === '3:1';
    const resource = port.type.split('_')[0] as keyof typeof RESOURCE_COLORS;

    return (
        <g className="port" data-port={port.type}>
            <title>{generic ? 'Any resource 3:1' : `${resource} 2:1`}</title>
            <line x1={anchor.x} y1={anchor.y} x2={first.x} y2={first.y} />
            <line x1={anchor.x} y1={anchor.y} x2={second.x} y2={second.y} />
            <circle
                cx={anchor.x}
                cy={anchor.y}
                r={HEX_SIZE * 0.3}
                fill={generic ? '#ffffff' : RESOURCE_COLORS[resource]}
            />
            <text x={anchor.x} y={anchor.y}>{generic ? '3:1' : '2:1'}</text>
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

export const Board = ({ game, players, targets, onSettlement, onRoad, onCity, onRobber }: BoardProps) => {
    const nameOf = (color: PlayerColor) => players.find((p) => p.color === color)?.name ?? color;

    return (
        <svg className="board" viewBox={VIEW_BOX} role="img" aria-label="Game board">
            {game.board_tiles.map((tile) => (
                <Tile
                    key={`${tile.hex.q}-${tile.hex.r}`}
                    tile={tile}
                    rolled={game.dice_roll !== null && tile.number === game.dice_roll}
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
