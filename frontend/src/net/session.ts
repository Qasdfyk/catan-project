import type { RoomSession } from '../types/game';

// sessionStorage keeps each browser tab a separate player, also in the same room.
const key = (roomId: string) => `catan_session_${roomId}`;

export const loadSession = (roomId: string): RoomSession | null => {
    const stored = sessionStorage.getItem(key(roomId));
    return stored ? (JSON.parse(stored) as RoomSession) : null;
};

export const saveSession = (session: RoomSession) => {
    sessionStorage.setItem(key(session.room_id), JSON.stringify(session));
};

export const clearSession = (roomId: string) => {
    sessionStorage.removeItem(key(roomId));
};
