import { Stage, Container, Graphics, Text } from '@pixi/react';
import { useCallback } from 'react';
// We import Graphics as 'PixiGraphics' to avoid conflict with the component 'Graphics'
import { TextStyle, Graphics as PixiGraphics, FederatedPointerEvent } from 'pixi.js';
import type { GameState, BoardTile } from '../types/game';
import { hexToPixel, getResourceColor, getEdgeCoords, getVertexCoords, HEX_SIZE } from '../utils/hexLayout';
import { useGame } from '../context/GameContext';

interface CatanBoardProps {
    gameState: GameState;
}

export const CatanBoard = ({ gameState }: CatanBoardProps) => {
    const { socket, playerId } = useGame();

    // Identify current player
    const currentPlayer = gameState.players[gameState.current_turn_index];
    // Safety check: ensure player exists before checking ID
    const isMyTurn = currentPlayer && playerId && currentPlayer.id === playerId;

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

    // Typed 'g' as PixiGraphics
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

        // Draw Robber
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
                
                {/* 1. LAYER: HEX TILES */}
                {gameState.board_tiles.map((tile) => {
                    const pos = hexToPixel(tile.hex);
                    const key = `hex-${tile.hex.q},${tile.hex.r},${tile.hex.s}`;

                    return (
                        <Container key={key} zIndex={1}>
                            {/* Explicitly typed callback */}
                            <Graphics draw={(g: PixiGraphics) => drawHex(g, tile)} />
                            
                            {tile.number !== null && (
                                <Text
                                    text={tile.number.toString()}
                                    x={pos.x}
                                    y={pos.y}
                                    anchor={0.5}
                                    style={
                                        new TextStyle({
                                            fontFamily: 'Arial',
                                            fontSize: 24,
                                            fontWeight: 'bold',
                                            fill: '#ffffff',
                                            stroke: '#000000',
                                            strokeThickness: 3,
                                        }) as any
                                    }
                                />
                            )}
                        </Container>
                    );
                })}

                {/* 2. LAYER: EDGES (ROADS & HITBOXES) */}
                {gameState.board_tiles.map((tile) => (
                    <Container key={`edges-${tile.hex.q}-${tile.hex.r}`} zIndex={5}>
                        {[0, 1, 2, 3, 4, 5].map(dir => {
                            const { x, y, rotation } = getEdgeCoords(tile.hex, dir);
                            
                            const existingRoad = gameState.roads.find(r => 
                                r.hex.q === tile.hex.q && 
                                r.hex.r === tile.hex.r && 
                                r.hex.s === tile.hex.s && 
                                r.direction === dir
                            );

                            return (
                                <Container key={`edge-${dir}`} x={x} y={y} rotation={rotation}>
                                    {/* A. VISUAL ROAD */}
                                    {existingRoad && (
                                        <Graphics draw={(g: PixiGraphics) => {
                                            g.clear();
                                            const c = existingRoad.color === 'red' ? 0xFF0000 :
                                                      existingRoad.color === 'blue' ? 0x0000FF :
                                                      existingRoad.color === 'white' ? 0xFFFFFF : 0xFFA500;
                                            g.beginFill(c);
                                            g.drawRect(-5, -20, 10, 40); 
                                            g.endFill();
                                        }} />
                                    )}

                                    {/* B. INTERACTION HITBOX */}
                                    {!existingRoad && (
                                        <Graphics 
                                            interactive={true}
                                            onclick={() => handleBuildRoad(tile.hex.q, tile.hex.r, tile.hex.s, dir)}
                                            draw={(g: PixiGraphics) => {
                                                g.clear();
                                                g.beginFill(0xFFFFFF, 0.01); 
                                                g.drawRect(-10, -20, 20, 40); 
                                                g.endFill();
                                            }}
                                            // Typed events
                                            mouseover={(e: FederatedPointerEvent) => { e.currentTarget.alpha = 0.5; }}
                                            mouseout={(e: FederatedPointerEvent) => { e.currentTarget.alpha = 1; }}
                                            cursor="pointer"
                                            visible={!!isMyTurn}
                                        />
                                    )}
                                </Container>
                            );
                        })}
                    </Container>
                ))}

                {/* 3. LAYER: VERTICES (SETTLEMENTS & HITBOXES) */}
                {gameState.board_tiles.map((tile) => (
                    <Container key={`verts-${tile.hex.q}-${tile.hex.r}`} zIndex={10}>
                         {[0, 1, 2, 3, 4, 5].map(dir => {
                            const { x, y } = getVertexCoords(tile.hex, dir);
                            
                            const existingBldg = gameState.settlements.find(s => 
                                s.hex.q === tile.hex.q && 
                                s.hex.r === tile.hex.r && 
                                s.hex.s === tile.hex.s && 
                                s.direction === dir
                            );

                            return (
                                <Container key={`vert-${dir}`} x={x} y={y}>
                                    {/* A. VISUAL BUILDING */}
                                    {existingBldg ? (
                                        <Graphics draw={(g: PixiGraphics) => {
                                            g.clear();
                                            const c = existingBldg.owner === 'red' ? 0xFF0000 :
                                                      existingBldg.owner === 'blue' ? 0x0000FF :
                                                      existingBldg.owner === 'white' ? 0xFFFFFF : 0xFFA500;
                                            g.beginFill(c);
                                            g.lineStyle(1, 0x000000);
                                            if(existingBldg.type === 'city') {
                                                g.drawRect(-12, -12, 24, 24);
                                            } else {
                                                g.drawCircle(0, 0, 10);
                                            }
                                            g.endFill();
                                        }} />
                                    ) : (
                                    /* B. INTERACTION HITBOX */
                                        <Graphics 
                                            interactive={true}
                                            onclick={() => handleBuildSettlement(tile.hex.q, tile.hex.r, tile.hex.s, dir)}
                                            draw={(g: PixiGraphics) => {
                                                g.clear();
                                                g.beginFill(0xFFFFFF, 0.3); 
                                                g.drawCircle(0, 0, 12);
                                                g.endFill();
                                            }}
                                            alpha={0} 
                                            mouseover={(e: FederatedPointerEvent) => { e.currentTarget.alpha = 1; }}
                                            mouseout={(e: FederatedPointerEvent) => { e.currentTarget.alpha = 0; }}
                                            cursor="pointer"
                                            visible={!!isMyTurn}
                                        />
                                    )}
                                </Container>
                            );
                         })}
                    </Container>
                ))}

            </Container>
        </Stage>
    );
};