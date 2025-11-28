import { createContext, useContext, useEffect, useState, useCallback, type ReactNode } from 'react';
import io, { Socket } from 'socket.io-client';
import type { GameState } from '../types/game';

interface GameContextType {
    socket: Socket;
    isConnected: boolean;
    gameState: GameState | null;
    playerId: string | null;
    setPlayerId: (id: string) => void;
    joinRoom: (roomId: string) => void;
}

const BACKEND_URL = 'http://localhost:8000';

const socket = io(BACKEND_URL, {
    autoConnect: false,
    transports: ['websocket']
});

const GameContext = createContext<GameContextType | undefined>(undefined);

export const GameProvider = ({ children }: { children: ReactNode }) => {
    const [isConnected, setIsConnected] = useState(false);
    const [gameState, setGameState] = useState<GameState | null>(null);
    const [playerId, setPlayerId] = useState<string | null>(localStorage.getItem('catan_player_id'));

    useEffect(() => {
        if (playerId) localStorage.setItem('catan_player_id', playerId);
    }, [playerId]);

    useEffect(() => {
        socket.connect();

        socket.on('connect', () => {
            console.log('✅ Socket connected:', socket.id);
            setIsConnected(true);
        });

        socket.on('disconnect', () => {
            console.log('❌ Socket disconnected');
            setIsConnected(false);
        });

        socket.on('game_state_update', (data: GameState) => {
            console.log('📥 Game State Updated');
            setGameState(data);
        });

        return () => {
            socket.off('connect');
            socket.off('disconnect');
            socket.off('game_state_update');
            socket.disconnect();
        };
    }, []);


    const joinRoom = useCallback((roomId: string) => {
        if (!socket.connected) socket.connect();
        socket.emit('join_game', { room_id: roomId });
    }, []); 

    return (
        <GameContext.Provider value={{ socket, isConnected, gameState, playerId, setPlayerId, joinRoom }}>
            {children}
        </GameContext.Provider>
    );
};

export const useGame = () => {
    const context = useContext(GameContext);
    if (!context) throw new Error("useGame must be used within a GameProvider");
    return context;
};