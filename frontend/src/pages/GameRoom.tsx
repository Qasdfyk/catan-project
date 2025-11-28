import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useGame } from '../context/GameContext';
import { CatanBoard } from '../components/CatanBoard';
import { GameInterface } from '../components/GameInterface';
import type { HexCoords } from '../types/game';

// Helper to format coordinates for display in debug view
const fmtHex = (h: HexCoords) => `q:${h.q}, r:${h.r}, s:${h.s}`;

export const GameRoom = () => {
    const { roomId } = useParams();
    const { socket, isConnected, gameState, joinRoom, playerId } = useGame();

    // 1. Join Room Logic
    useEffect(() => {
        if (roomId && isConnected) {
            console.log(`Attempting to join socket room: ${roomId}`);
            joinRoom(roomId);
        }
    }, [roomId, isConnected, joinRoom]);

    // 2. Error Handling
    useEffect(() => {
        socket.on('game_error', (data: { message: string }) => {
            alert(`❌ Game Error: ${data.message}`);
        });
        return () => { socket.off('game_error'); };
    }, [socket]);

    // 3. Action Handlers
    const handleRollDice = () => {
        if (!roomId) return;
        socket.emit('game_action', { room_id: roomId, type: 'roll_dice', payload: {} });
    };

    const handleEndTurn = () => {
        if (!roomId) return;
        socket.emit('game_action', { room_id: roomId, type: 'end_turn', payload: {} });
    };

    // --- RENDER WAITING STATE ---
    if (!isConnected) return <div style={{padding: 20}}>🔴 Connecting to server...</div>;

    if (!gameState) {
        return (
            <div style={{padding: 20, textAlign: 'center'}}>
                <h2>⏳ Joining Room...</h2>
                <p>Room ID: {roomId}</p>
                <button onClick={() => roomId && joinRoom(roomId)}>Retry Join</button>
            </div>
        );
    }

    // --- RENDER GAME STATE ---
    return (
        <div style={{ padding: '20px', maxWidth: '1200px', margin: '0 auto', fontFamily: 'sans-serif' }}>
            
            {/* GAME CONTAINER (BOARD + HUD) */}
            <div style={{ 
                position: 'relative', 
                width: '800px', 
                height: '600px', 
                margin: '0 auto 20px auto', 
                border: '4px solid #333',
                borderRadius: '8px',
                overflow: 'hidden',
                backgroundColor: '#87CEEB',
                boxShadow: '0 10px 30px rgba(0,0,0,0.5)'
            }}>
                {/* 1. THE BOARD */}
                <CatanBoard gameState={gameState} />

                {/* 2. THE UI OVERLAY */}
                <GameInterface 
                    gameState={gameState} 
                    onRoll={handleRollDice} 
                    onEndTurn={handleEndTurn} 
                />
            </div>

            {/* DEBUG / INFO SECTION */}
            <details style={{ background: '#f4f4f4', padding: '15px', borderRadius: '8px' }}>
                <summary style={{cursor: 'pointer', fontWeight: 'bold'}}>🛠️ Debug Info & Player Stats</summary>

                <div style={{marginTop: '10px', padding: '10px', background: '#ffebee', border: '1px solid #ffcdd2'}}>
                    <strong>🕵️ Identity Switcher (For testing without Auth):</strong>
                    <div style={{display: 'flex', gap: '10px', marginTop: '5px'}}>
                        {gameState.players.map(p => (
                            <button 
                                key={p.id}
                                onClick={() => {
                                    // setPlayerId musi być wyciągnięte z useGame() na górze pliku!
                                    // const { ..., setPlayerId } = useGame();
                                    // Tutaj używamy window.location.reload() żeby odświeżyć kontekst
                                    localStorage.setItem('catan_player_id', p.id);
                                    window.location.reload();
                                }}
                                disabled={p.id === playerId}
                                style={{
                                    padding: '5px 10px', 
                                    cursor: 'pointer',
                                    fontWeight: p.id === playerId ? 'bold' : 'normal',
                                    border: p.id === playerId ? '2px solid green' : '1px solid #ccc'
                                }}
                            >
                                Play as {p.name}
                            </button>
                        ))}
                    </div>
                </div>
                
                <div style={{ marginTop: '15px', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                    <div>
                        <h4>Info</h4>
                        <p><strong>My ID:</strong> {playerId}</p>
                        <p><strong>Room:</strong> {roomId}</p>
                        <p><strong>Robber:</strong> {gameState.robber_hex ? fmtHex(gameState.robber_hex) : "None"}</p>
                    </div>
                    <div>
                         <h4>Players</h4>
                         {gameState.players.map(p => (
                            <div key={p.id} style={{fontSize: '12px', marginBottom: '5px'}}>
                                {p.name} ({p.color}): {p.victory_points} VP - Res: {JSON.stringify(p.resources)}
                            </div>
                         ))}
                    </div>
                </div>
            </details>
        </div>
    );
};