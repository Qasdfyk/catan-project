import { useState, useEffect } from 'react';
import io, { Socket } from 'socket.io-client';

// 1. Definicje typów (normalnie byłyby w src/types/game.ts)
interface GameResponse {
  room_id: string;
  status: string;
  created_at: string;
  players: string[];
}

// 2. Konfiguracja Socket.IO
// Łączymy się z localhost:8000 (Twoim Dockerem)
const BACKEND_URL = 'http://localhost:8000';
const socket: Socket = io(BACKEND_URL, {
  autoConnect: false // Nie łączymy automatycznie przy starcie
});

function App() {
  // --- STAN APLIKACJI ---
  const [isConnected, setIsConnected] = useState(socket.connected);
  const [playerNames, setPlayerNames] = useState<string>('Neo, Morpheus');
  const [gameData, setGameData] = useState<GameResponse | null>(null);
  const [error, setError] = useState<string>('');
  const [loading, setLoading] = useState(false);

  // --- OBSŁUGA SOCKETÓW ---
  useEffect(() => {
    // Włączamy nasłuchiwanie
    socket.connect();

    socket.on('connect', () => {
      console.log('🟢 WebSocket Connected! ID:', socket.id);
      setIsConnected(true);
    });

    socket.on('disconnect', () => {
      console.log('🔴 WebSocket Disconnected');
      setIsConnected(false);
    });

    // Sprzątanie przy zamknięciu strony
    return () => {
      socket.off('connect');
      socket.off('disconnect');
      socket.disconnect();
    };
  }, []);

  // --- KOMUNIKACJA Z REST API ---
  const handleCreateGame = async () => {
    setLoading(true);
    setError('');
    setGameData(null);

    // Zamiana stringa "Adam, Ewa" na tablicę ["Adam", "Ewa"]
    const namesArray = playerNames.split(',').map(n => n.trim()).filter(n => n.length > 0);

    if (namesArray.length < 2) {
      setError("Podaj przynajmniej 2 graczy!");
      setLoading(false);
      return;
    }

    try {
      // Uderzamy do Twojego endpointu w Pythonie
      const response = await fetch(`${BACKEND_URL}/api/games`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ player_names: namesArray }),
      });

      if (!response.ok) {
        throw new Error('Błąd tworzenia gry (sprawdź logi Dockera)');
      }

      const data: GameResponse = await response.json();
      setGameData(data);
      console.log("Gra utworzona:", data);

    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  // --- WIDOK (HTML) ---
  return (
    <div style={{ maxWidth: '600px', margin: '50px auto', fontFamily: 'sans-serif', textAlign: 'center' }}>
      <h1>🏰 Catan: Faza 4</h1>
      
      {/* Pasek statusu */}
      <div style={{ 
        padding: '10px', margin: '20px 0', borderRadius: '5px',
        background: isConnected ? '#d4edda' : '#f8d7da',
        color: isConnected ? '#155724' : '#721c24'
      }}>
        Status WebSocketa: <strong>{isConnected ? 'POŁĄCZONO' : 'ROZŁĄCZONO'}</strong>
      </div>

      {/* Formularz */}
      <div style={{ border: '1px solid #ccc', padding: '20px', borderRadius: '10px' }}>
        <h3>Stwórz nową grę</h3>
        <input 
          type="text" 
          value={playerNames}
          onChange={(e) => setPlayerNames(e.target.value)}
          style={{ padding: '10px', width: '80%', marginBottom: '10px' }}
          placeholder="Wpisz imiona graczy..."
        />
        <br />
        <button 
          onClick={handleCreateGame} 
          disabled={loading || !isConnected}
          style={{ 
            padding: '10px 20px', fontSize: '16px', cursor: 'pointer',
            backgroundColor: isConnected ? '#007bff' : '#ccc', color: 'white', border: 'none'
          }}
        >
          {loading ? 'Tworzenie...' : 'Wyślij do API (POST)'}
        </button>

        {error && <p style={{ color: 'red' }}>{error}</p>}
      </div>

      {/* Wynik */}
      {gameData && (
        <div style={{ marginTop: '30px', padding: '20px', backgroundColor: '#f0f0f0', borderRadius: '10px' }}>
          <h2>✅ Sukces!</h2>
          <p>ID Pokoju: <strong>{gameData.room_id}</strong></p>
          <p>Gracze: {gameData.players.join(', ')}</p>
          <p style={{ fontSize: '12px', color: '#666' }}>Dane pobrane z Redis via Python API</p>
        </div>
      )}
    </div>
  );
}

export default App;