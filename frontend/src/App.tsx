import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { GameProvider } from './context/GameContext';
import { Lobby } from './pages/Lobby';
import { GameRoom } from './pages/GameRoom';
import './App.css';

function App() {
  return (
    <GameProvider>
      {/* 2. BrowserRouter obsługuje zmianę URL w przeglądarce */}
      <BrowserRouter>
        <Routes>
          {/* Strona startowa - Lobby */}
          <Route path="/" element={<Lobby />} />
          
          {/* Pokój gry z dynamicznym ID */}
          <Route path="/game/:roomId" element={<GameRoom />} />
          
          {/* Przekierowanie nieznanych adresów do Lobby */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </GameProvider>
  );
}

export default App;