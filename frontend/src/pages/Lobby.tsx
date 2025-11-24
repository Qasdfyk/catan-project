import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useGame } from '../context/GameContext';
import type { GameCreateResponse } from '../types/game';

export const Lobby = () => {
    const [playerNames, setPlayerNames] = useState('Alice, Bob');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState('');
    const { isConnected } = useGame();
    const navigate = useNavigate();

    const handleCreateGame = async () => {
        setLoading(true);
        setError('');
        
        const namesArray = playerNames.split(',').map(n => n.trim()).filter(n => n.length > 0);
        if (namesArray.length < 2) {
             setError("At least 2 players are required.");
             setLoading(false);
             return;
        }

        try {
            const response = await fetch('http://localhost:8000/api/games', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ player_names: namesArray }),
            });

            if (!response.ok) {
                const errText = await response.text();
                throw new Error(`API Error: ${errText}`);
            }

            const data: GameCreateResponse = await response.json();
            
            // Redirect to Game Room
            navigate(`/game/${data.room_id}`);

        } catch (err: any) {
            setError(err.message);
        } finally {
            setLoading(false);
        }
    };

    return (
        <div style={{ textAlign: 'center', marginTop: '50px', fontFamily: 'sans-serif' }}>
            <h1>🏰 Catan Lobby (Phase 4)</h1>
            
            <div style={{ 
                margin: '10px auto', width: 'fit-content', padding: '5px 15px', borderRadius: '4px',
                background: isConnected ? '#d4edda' : '#f8d7da',
                color: isConnected ? '#155724' : '#721c24'
            }}>
                WebSocket Status: <strong>{isConnected ? 'ONLINE' : 'OFFLINE'}</strong>
            </div>
            
            <div style={{ margin: '20px auto', padding: '20px', border: '1px solid #ccc', maxWidth: '400px', borderRadius: '8px' }}>
                <label style={{display: 'block', marginBottom: '10px'}}>Player Names (comma separated):</label>
                <input 
                    value={playerNames} 
                    onChange={e => setPlayerNames(e.target.value)}
                    placeholder="e.g. Neo, Morpheus"
                    style={{ width: '100%', padding: '8px', boxSizing: 'border-box' }}
                />
                <br /><br />
                <button 
                    onClick={handleCreateGame} 
                    disabled={loading || !isConnected}
                    style={{ padding: '10px 20px', cursor: 'pointer', background: '#007bff', color: '#fff', border: 'none', borderRadius: '4px'}}
                >
                    {loading ? 'Creating...' : 'Create Game (POST)'}
                </button>
                {error && <p style={{color: 'red', marginTop: '10px'}}>{error}</p>}
            </div>
        </div>
    );
};