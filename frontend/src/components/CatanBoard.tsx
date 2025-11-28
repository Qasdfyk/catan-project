import { Stage, Container, Graphics, Text } from '@pixi/react';
import { useCallback } from 'react';
import { TextStyle, Graphics as PixiGraphics, FederatedPointerEvent } from 'pixi.js';
import type { GameState, BoardTile, HexCoords } from '../types/game';
import { hexToPixel, getResourceColor, getEdgeCoords, getVertexCoords, HEX_SIZE } from '../utils/hexLayout';
import { useGame } from '../context/GameContext';

interface CatanBoardProps {
    gameState: GameState;
}

export const CatanBoard = ({ gameState }: CatanBoardProps) => {
    const { socket, playerId } = useGame();

    const currentPlayer = gameState.players[gameState.current_turn_index];
    const isMyTurn = currentPlayer && playerId && currentPlayer.id === playerId;

    // --- HANDLERS ---
    const handleBuildRoad = (q: number, r: number, s: number, dir: number) => {
        if (!isMyTurn) return;
        socket.emit('game_action', {
            room_id: window.location.pathname.split('/').pop(), 
            type: 'build_road',
            payload: { hex: {q,r,s}, direction: dir }
        });
    };

    const handleBuildSettlement = (q: number, r: number, s: number, dir: number) => {
        if (!isMyTurn) return;
        socket.emit('game_action', {
            room_id: window.location.pathname.split('/').pop(),
            type: 'build_settlement',
            payload: { hex: {q,r,s}, direction: dir }
        });
    };

    const handleUpgradeCity = (q: number, r: number, s: number, dir: number) => {
        if (!isMyTurn) return;
        socket.emit('game_action', {
            room_id: window.location.pathname.split('/').pop(),
            type: 'upgrade_city',
            payload: { hex: {q,r,s}, direction: dir }
        });
    };

    // --- HELPERS ---
    const isOccupiedVertex = (h: HexCoords, dir: number) => {
        return gameState.settlements.some(s => 
            s.hex.q === h.q && s.hex.r === h.r && s.hex.s === h.s && s.direction === dir
        );
    };

    const isOccupiedEdge = (h: HexCoords, dir: number) => {
        // Warning: This only checks exact matches. 
        // Ideally we should check canonical, but for hiding hitboxes this is mostly fine.
        return gameState.roads.some(r => 
            r.hex.q === h.q && r.hex.r === h.r && r.hex.s === h.s && r.direction === dir
        );
    };

    const drawHex = useCallback((g: PixiGraphics, tile: BoardTile) => {
        const { x, y } = hexToPixel(tile.hex);
        const color = getResourceColor(tile.resource);
        const colorNumber = parseInt(color.replace('#', ''), 16);

        g.clear();
        g.beginFill(colorNumber);
        g.lineStyle(2, 0x333333, 1);

        const points = [];
        for (let i = 0; i < 6; i++) {
            const angle_deg = 60 * i - 30;
            const angle_rad = Math.PI / 180 * angle_deg;
            points.push(
                x + HEX_SIZE * Math.cos(angle_rad),
                y + HEX_SIZE * Math.sin(angle_rad)
            );
        }
        g.drawPolygon(points);
        g.endFill();

        if (gameState.robber_hex && 
            gameState.robber_hex.q === tile.hex.q && 
            gameState.robber_hex.r === tile.hex.r && 
            gameState.robber_hex.s === tile.hex.s) {
            
            g.beginFill(0x000000, 0.5);
            g.drawCircle(x, y, 20);
            g.endFill();
        }

    }, [gameState.robber_hex]);

    return (
        <Stage width={800} height={600} options={{ backgroundColor: 0x87CEEB }}>
            <Container sortableChildren={true}>
                
                {/* 1. TILES */}
                {gameState.board_tiles.map((tile) => {
                    const pos = hexToPixel(tile.hex);
                    const key = `hex-${tile.hex.q},${tile.hex.r},${tile.hex.s}`;
                    return (
                        <Container key={key} zIndex={1}>
                            <Graphics draw={(g: PixiGraphics) => drawHex(g, tile)} />
                            {tile.number !== null && (
                                <Text
                                    text={tile.number.toString()}
                                    x={pos.x} y={pos.y} anchor={0.5}
                                    style={new TextStyle({
                                        fontFamily: 'Arial', fontSize: 24, fontWeight: 'bold',
                                        fill: '#ffffff', stroke: '#000000', strokeThickness: 3,
                                    }) as any}
                                />
                            )}
                        </Container>
                    );
                })}

                {/* 2. EXISTING ROADS (DRAWN FROM STATE) */}
                <Container zIndex={5}>
                    {gameState.roads.map((road, i) => {
                        const { x, y, rotation } = getEdgeCoords(road.hex, road.direction);
                        return (
                            <Container key={`road-${i}`} x={x} y={y} rotation={rotation}>
                                <Graphics draw={(g: PixiGraphics) => {
                                    g.clear();
                                    const c = road.color === 'red' ? 0xFF0000 :
                                              road.color === 'blue' ? 0x0000FF :
                                              road.color === 'white' ? 0xFFFFFF : 0xFFA500;
                                    g.beginFill(c);
                                    g.drawRect(-5, -20, 10, 40); 
                                    g.endFill();
                                }} />
                            </Container>
                        );
                    })}
                </Container>

                {/* 3. ROAD HITBOXES (EMPTY SPOTS) */}
                <Container zIndex={6}>
                    {gameState.board_tiles.map((tile) => (
                        [0, 1, 2, 3, 4, 5].map(dir => {
                            if (isOccupiedEdge(tile.hex, dir)) return null; // Simple visual hide
                            const { x, y, rotation } = getEdgeCoords(tile.hex, dir);
                            return (
                                <Container key={`edge-hitbox-${tile.hex.q}-${tile.hex.r}-${dir}`} x={x} y={y} rotation={rotation}>
                                    <Graphics 
                                        interactive={true}
                                        onclick={() => handleBuildRoad(tile.hex.q, tile.hex.r, tile.hex.s, dir)}
                                        draw={(g: PixiGraphics) => {
                                            g.clear();
                                            g.beginFill(0xFFFFFF, 0.01); 
                                            g.drawRect(-10, -20, 20, 40); 
                                            g.endFill();
                                        }}
                                        mouseover={(e: FederatedPointerEvent) => { (e.currentTarget as PixiGraphics).alpha = 0.5; }}
                                        mouseout={(e: FederatedPointerEvent) => { (e.currentTarget as PixiGraphics).alpha = 1; }}
                                        cursor={isMyTurn ? "pointer" : "default"}
                                        visible={!!isMyTurn}
                                    />
                                </Container>
                            );
                        })
                    ))}
                </Container>

                {/* 4. VERTEX HITBOXES (EMPTY SPOTS) */}
                <Container zIndex={10}>
                    {gameState.board_tiles.map((tile) => (
                         [0, 1, 2, 3, 4, 5].map(dir => {
                            if (isOccupiedVertex(tile.hex, dir)) return null;
                            const { x, y } = getVertexCoords(tile.hex, dir);
                            return (
                                <Container key={`vert-hitbox-${tile.hex.q}-${tile.hex.r}-${dir}`} x={x} y={y}>
                                    <Graphics 
                                        interactive={true}
                                        onclick={() => handleBuildSettlement(tile.hex.q, tile.hex.r, tile.hex.s, dir)}
                                        draw={(g: PixiGraphics) => {
                                            g.clear();
                                            g.beginFill(0xFFFFFF, 0.4); 
                                            g.drawCircle(0, 0, 12);
                                            g.endFill();
                                        }}
                                        alpha={0}
                                        mouseover={(e: FederatedPointerEvent) => { (e.currentTarget as PixiGraphics).alpha = 1; }}
                                        mouseout={(e: FederatedPointerEvent) => { (e.currentTarget as PixiGraphics).alpha = 0; }}
                                        cursor={isMyTurn ? "pointer" : "default"}
                                        visible={!!isMyTurn}
                                    />
                                </Container>
                            );
                         })
                    ))}
                </Container>

                {/* 5. EXISTING SETTLEMENTS (DRAWN FROM STATE) */}
                <Container zIndex={20}>
                    {gameState.settlements.map((bldg, i) => {
                        const { x, y } = getVertexCoords(bldg.hex, bldg.direction);
                        const canUpgrade = isMyTurn && bldg.type === 'settlement' && bldg.owner === currentPlayer?.color;

                        return (
                            <Container key={`bldg-${i}`} x={x} y={y}>
                                <Graphics 
                                    interactive={canUpgrade ? true : false}
                                    cursor={canUpgrade ? "pointer" : "default"}
                                    onclick={() => {
                                        if (canUpgrade) handleUpgradeCity(bldg.hex.q, bldg.hex.r, bldg.hex.s, bldg.direction);
                                    }}
                                    mouseover={(e: FederatedPointerEvent) => { 
                                        if (canUpgrade) (e.currentTarget as PixiGraphics).alpha = 0.8; 
                                    }}
                                    mouseout={(e: FederatedPointerEvent) => { (e.currentTarget as PixiGraphics).alpha = 1; }}
                                    draw={(g: PixiGraphics) => {
                                        g.clear();
                                        const c = bldg.owner === 'red' ? 0xFF0000 :
                                                  bldg.owner === 'blue' ? 0x0000FF :
                                                  bldg.owner === 'white' ? 0xFFFFFF : 0xFFA500;
                                        g.beginFill(c);
                                        g.lineStyle(2, 0x000000);
                                        if(bldg.type === 'city') g.drawRect(-12, -12, 24, 24);
                                        else g.drawCircle(0, 0, 10);
                                        g.endFill();
                                    }} 
                                />
                            </Container>
                        );
                    })}
                </Container>

            </Container>
        </Stage>
    );
};