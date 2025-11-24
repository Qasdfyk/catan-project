import { Stage, Container, Graphics, Text } from '@pixi/react';
import { useCallback } from 'react';
// 1. Importujemy TextStyle z pixi.js
import { TextStyle } from 'pixi.js';
import type { GameState, BoardTile } from '../types/game';
import { hexToPixel, getResourceColor, HEX_SIZE } from '../utils/hexLayout';

interface CatanBoardProps {
    gameState: GameState;
}

export const CatanBoard = ({ gameState }: CatanBoardProps) => {
    
    const drawHex = useCallback((g: any, tile: BoardTile) => {
        const { x, y } = hexToPixel(tile.hex);
        const color = getResourceColor(tile.resource);

        // Zamiana koloru HEX string na number
        const colorNumber = parseInt(color.replace('#', ''), 16);

        g.clear();
        
        // Wypełnienie i obrys
        g.beginFill(colorNumber);
        g.lineStyle(2, 0x333333, 1);

        // Rysowanie wielokąta
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

        // Rysowanie Robbera
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
                {gameState.board_tiles.map((tile) => {
                    const pos = hexToPixel(tile.hex);
                    const key = `${tile.hex.q},${tile.hex.r},${tile.hex.s}`;

                    return (
                        <Container key={key} zIndex={1}>
                            <Graphics draw={(g) => drawHex(g, tile)} />
                            
                            {tile.number !== null && (
                                <Text
                                    text={tile.number.toString()}
                                    x={pos.x}
                                    y={pos.y}
                                    anchor={0.5}
                                    // 2. KLUCZOWA POPRAWKA:
                                    // Tworzymy new TextStyle i rzutujemy na 'any', 
                                    // aby ominąć konflikt typów TypeScripta.
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
            </Container>
        </Stage>
    );
};