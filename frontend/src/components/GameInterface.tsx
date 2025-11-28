import type { GameState, ResourceType } from '../types/game';
import { useGame } from '../context/GameContext';
import { useMemo } from 'react';

interface GameInterfaceProps {
    gameState: GameState;
    onRoll: () => void;
    onEndTurn: () => void;
}

export const GameInterface = ({ gameState, onRoll, onEndTurn }: GameInterfaceProps) => {
    const { playerId } = useGame();
    
    // Identify current player and "Me"
    const currentPlayer = gameState.players[gameState.current_turn_index];
    const isMyTurn = currentPlayer?.id === playerId;
    const me = useMemo(() => gameState.players.find(p => p.id === playerId), [gameState.players, playerId]);

    // Helper to get my resource count safely
    const getRes = (type: string) => me?.resources[type as ResourceType] || 0;

    // Helper for resource colors
    const getResourceColor = (res: string) => {
        switch (res) {
            case 'wood': return '#228B22';
            case 'brick': return '#B22222';
            case 'sheep': return '#9ACD32';
            case 'wheat': return '#FFD700';
            case 'ore': return '#708090';
            default: return '#ccc';
        }
    };

    return (
        <div style={{
            position: 'absolute',
            top: 0, left: 0, right: 0, bottom: 0,
            pointerEvents: 'none', // Let clicks pass through to the canvas
            padding: '20px',
            display: 'flex',
            flexDirection: 'column',
            justifyContent: 'space-between',
            fontFamily: 'sans-serif'
        }}>
            
            {/* TOP BAR: GAME INFO */}
            <div style={{ 
                background: 'rgba(0,0,0,0.8)', color: 'white', 
                padding: '10px 20px', borderRadius: '8px', pointerEvents: 'auto',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                boxShadow: '0 2px 10px rgba(0,0,0,0.3)'
            }}>
                <div style={{ display: 'flex', alignItems: 'center', gap: '20px' }}>
                    <div>
                        <span style={{color: '#aaa', fontSize: '0.8em'}}>TURN</span><br/>
                        <strong style={{color: currentPlayer?.color === 'white' ? '#eee' : currentPlayer?.color, fontSize: '1.2em'}}>
                            {currentPlayer?.name}
                        </strong>
                    </div>
                    
                    <div style={{borderLeft: '1px solid #555', paddingLeft: '20px'}}>
                        <span style={{color: '#aaa', fontSize: '0.8em'}}>PHASE</span><br/>
                        <strong>{gameState.turn_phase.toUpperCase().replace('_', ' ')}</strong>
                    </div>

                    {/* SETUP PHASE INSTRUCTION */}
                    {gameState.turn_phase === 'setup' && isMyTurn && (
                        <div style={{
                            marginLeft: '20px', background: '#ffcc00', color: 'black', 
                            padding: '5px 10px', borderRadius: '4px', fontWeight: 'bold'
                        }}>
                            ACTION: {gameState.setup_waiting_for_road ? "PLACE A ROAD" : "PLACE A SETTLEMENT"}
                        </div>
                    )}
                </div>

                <div style={{textAlign: 'right'}}>
                     <span style={{color: '#aaa', fontSize: '0.8em'}}>MY POINTS</span><br/>
                     <strong style={{fontSize: '1.5em', color: '#4caf50'}}>{me?.victory_points || 0}</strong>
                </div>
            </div>

            {/* BOTTOM BAR: HAND & ACTIONS */}
            <div style={{ 
                background: 'rgba(255,255,255,0.95)', 
                padding: '15px 20px', borderRadius: '8px', pointerEvents: 'auto',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center',
                boxShadow: '0 -2px 10px rgba(0,0,0,0.2)'
            }}>
                
                {/* RESOURCES */}
                <div style={{display: 'flex', gap: '15px'}}>
                    {['wood', 'brick', 'sheep', 'wheat', 'ore'].map(res => (
                        <div key={res} style={{textAlign: 'center', position: 'relative'}}>
                            <div style={{
                                width: '50px', height: '60px', 
                                background: getResourceColor(res), 
                                borderRadius: '6px', border: '2px solid #555',
                                marginBottom: '5px', display: 'flex', alignItems: 'center', justifyContent: 'center',
                                color: 'white', textShadow: '1px 1px 0 #000', fontWeight: 'bold', fontSize: '1.2em'
                            }}>
                                {getRes(res)}
                            </div>
                            <div style={{fontSize: '10px', textTransform: 'uppercase', fontWeight: 'bold', color: '#333'}}>{res}</div>
                        </div>
                    ))}
                </div>

                {/* ACTION BUTTONS */}
                <div style={{display: 'flex', gap: '10px'}}>
                    {gameState.turn_phase === 'roll_dice' && (
                        <button 
                            onClick={onRoll} 
                            disabled={!isMyTurn}
                            style={{
                                padding: '15px 30px', fontSize: '18px', fontWeight: 'bold',
                                cursor: isMyTurn ? 'pointer' : 'not-allowed',
                                background: isMyTurn ? '#007bff' : '#ccc',
                                color: 'white', border: 'none', borderRadius: '6px',
                                boxShadow: '0 4px 0 rgba(0,0,0,0.2)'
                            }}
                        >
                            🎲 ROLL DICE
                        </button>
                    )}
                    
                    {gameState.turn_phase === 'main_phase' && (
                        <button 
                            onClick={onEndTurn} 
                            disabled={!isMyTurn}
                            style={{
                                padding: '15px 30px', fontSize: '18px', fontWeight: 'bold',
                                cursor: isMyTurn ? 'pointer' : 'not-allowed',
                                background: isMyTurn ? '#dc3545' : '#ccc',
                                color: 'white', border: 'none', borderRadius: '6px',
                                boxShadow: '0 4px 0 rgba(0,0,0,0.2)'
                            }}
                        >
                            🛑 END TURN
                        </button>
                    )}
                </div>
            </div>
        </div>
    );
};