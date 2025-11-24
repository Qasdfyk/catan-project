import { useEffect } from 'react';
import { useParams } from 'react-router-dom';
import { useGame } from '../context/GameContext';
import { CatanBoard } from '../components/CatanBoard';
import type { HexCoords } from '../types/game';

// Helper to format coordinates for display in debug view
const fmtHex = (h: HexCoords) => `q:${h.q}, r:${h.r}, s:${h.s}`;

export const GameRoom = () => {
    const { roomId } = useParams();
    const { socket, isConnected, gameState, joinRoom } = useGame();

    // 1. Join Room Logic
    useEffect(() => {
        if (roomId && isConnected) {
            console.log(`Attempting to join socket room: ${roomId}`);
            joinRoom(roomId);
        }
    }, [roomId, isConnected, joinRoom]);

    // 2. Error Handling Listener
    useEffect(() => {
        socket.on('game_error', (data: { message: string }) => {
            alert(`❌ Game Error: ${data.message}`);
        });
        return () => { socket.off('game_error'); };
    }, [socket]);

    // 3. Action Handlers
    const handleRollDice = () => {
        if (!roomId) return;
        console.log("Emitting roll_dice action...");
        socket.emit('game_action', {
            room_id: roomId,
            type: 'roll_dice',
            payload: {}
        });
    };

    const handleEndTurn = () => {
        if (!roomId) return;
        console.log("Emitting end_turn action...");
        socket.emit('game_action', {
            room_id: roomId,
            type: 'end_turn',
            payload: {}
        });
    };

    // --- RENDER WAITING STATE ---
    if (!isConnected) {
        return <div style={{padding: 20}}>🔴 No connection to WebSocket server...</div>;
    }

    if (!gameState) {
        return (
            <div style={{padding: 20}}>
                <h2>⏳ Waiting for game state...</h2>
                <p>Room ID: {roomId}</p>
                <p>Check JS console and backend logs to see if 'join_game' event fired.</p>
                <button onClick={() => roomId && joinRoom(roomId)}>Retry Join</button>
            </div>
        );
    }

    // --- RENDER GAME STATE ---
    return (
        <div style={{ padding: '20px', fontFamily: 'monospace', maxWidth: '1200px', margin: '0 auto' }}>
            <header style={{ borderBottom: '2px solid #333', marginBottom: '20px', paddingBottom: '10px' }}>
                <h1 style={{margin: 0}}>🛠️ Debug Room: {roomId}</h1>
                <div style={{ display: 'flex', gap: '20px', marginTop: '10px' }}>
                    <span><strong>Phase:</strong> {gameState.turn_phase}</span>
                    <span><strong>Turn Idx:</strong> {gameState.current_turn_index}</span>
                    <span><strong>Dice:</strong> {gameState.dice_roll ?? "N/A"}</span>
                    <span><strong>Game Over:</strong> {gameState.is_game_over ? "YES" : "NO"}</span>
                </div>
            </header>

            {/* --- NEW VISUALS SECTION (PIXI.JS) --- */}
            <div style={{ 
                display: 'flex', 
                justifyContent: 'center', 
                marginBottom: '30px', 
                border: '4px solid #333', 
                borderRadius: '10px', 
                overflow: 'hidden',
                background: '#87CEEB'
            }}>
                <CatanBoard gameState={gameState} />
            </div>
            {/* ------------------------------------- */}

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '20px' }}>
                
                {/* LEFT COLUMN: PLAYERS & BUILDINGS */}
                <div>
                    <section style={{ background: '#f4f4f4', padding: '15px', borderRadius: '8px', marginBottom: '20px' }}>
                        <h3>👥 Players ({gameState.players.length})</h3>
                        {gameState.players.map(p => (
                            <div key={p.id} style={{ 
                                borderLeft: `5px solid ${p.color}`, 
                                padding: '10px', background: 'white', marginBottom: '5px' 
                            }}>
                                <strong>{p.name}</strong> ({p.color}) - VP: {p.victory_points}<br/>
                                <small>ID: {p.id}</small>
                                <div style={{ marginTop: '5px' }}>
                                    Resources: {JSON.stringify(p.resources)}
                                </div>
                            </div>
                        ))}
                    </section>

                    <section style={{ background: '#e8f4f8', padding: '15px', borderRadius: '8px' }}>
                        <h3>🏠 Buildings & Roads</h3>
                        <h4>Settlements ({gameState.settlements.length})</h4>
                        <ul>
                            {gameState.settlements.length === 0 && <li>No settlements</li>}
                            {gameState.settlements.map((s, i) => (
                                <li key={i}>
                                    {s.type} ({s.owner}) @ {fmtHex(s.hex)} / dir: {s.direction}
                                </li>
                            ))}
                        </ul>

                        <h4>Roads ({gameState.roads.length})</h4>
                        <ul>
                            {gameState.roads.length === 0 && <li>No roads</li>}
                            {gameState.roads.map((r, i) => (
                                <li key={i}>
                                    Road ({r.color}) @ {fmtHex(r.hex)} / dir: {r.direction}
                                </li>
                            ))}
                        </ul>
                    </section>
                </div>

                {/* RIGHT COLUMN: MAP (DEBUG DATA) */}
                <div>
                    <section style={{ background: '#fff3cd', padding: '15px', borderRadius: '8px', maxHeight: '80vh', overflowY: 'auto' }}>
                        <h3>🗺️ Board Tiles ({gameState.board_tiles.length})</h3>
                        <p><small>Robber Position: {gameState.robber_hex ? fmtHex(gameState.robber_hex) : "None"}</small></p>
                        
                        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                            <thead>
                                <tr style={{ textAlign: 'left', borderBottom: '1px solid #999' }}>
                                    <th>Coords (q,r,s)</th>
                                    <th>Resource</th>
                                    <th>Number</th>
                                </tr>
                            </thead>
                            <tbody>
                                {gameState.board_tiles.map((tile, i) => (
                                    <tr key={i} style={{ borderBottom: '1px solid #ddd' }}>
                                        <td>{fmtHex(tile.hex)}</td>
                                        <td style={{ fontWeight: 'bold', color: tile.resource === 'desert' ? '#888' : 'black' }}>
                                            {tile.resource}
                                        </td>
                                        <td>{tile.number ?? "-"}</td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </section>
                </div>

            </div>
            
            <footer style={{ marginTop: '30px', borderTop: '2px solid #333', paddingTop: '20px' }}>
                <h3>⚡ Dev Actions</h3>
                
                {/* ACTION BUTTONS */}
                <button 
                    onClick={handleRollDice} 
                    disabled={gameState.turn_phase !== 'roll_dice'}
                    style={{ 
                        padding: '10px 20px', 
                        fontSize: '16px', 
                        cursor: 'pointer', 
                        marginRight: '10px',
                        background: gameState.turn_phase === 'roll_dice' ? '#007bff' : '#ccc',
                        color: 'white',
                        border: 'none',
                        borderRadius: '5px'
                    }}
                >
                    🎲 Roll Dice
                </button>

                <button 
                    onClick={handleEndTurn}
                    disabled={gameState.turn_phase !== 'main_phase'}
                    style={{ 
                        padding: '10px 20px', 
                        fontSize: '16px', 
                        cursor: 'pointer', 
                        marginRight: '10px',
                        background: gameState.turn_phase === 'main_phase' ? '#dc3545' : '#ccc',
                        color: 'white',
                        border: 'none',
                        borderRadius: '5px'
                    }}
                >
                    🛑 End Turn
                </button>

                <button onClick={() => console.log(gameState)}>Log State to Console</button>
            </footer>
        </div>
    );
};