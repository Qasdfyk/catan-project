import type { RoomSession, RoomSummary } from '../types/game';

const request = async <T>(path: string, init?: RequestInit): Promise<T> => {
    let response: Response;
    try {
        response = await fetch(path, {
            ...init,
            headers: { 'Content-Type': 'application/json' },
        });
    } catch {
        throw new Error('Cannot reach the server.');
    }

    const body = await response.json().catch(() => null);
    if (!response.ok) {
        throw new Error(body?.detail ?? 'Something went wrong on the server.');
    }
    return body as T;
};

const withName = (name: string): RequestInit => ({
    method: 'POST',
    body: JSON.stringify({ name }),
});

export const createRoom = (name: string) => request<RoomSession>('/api/rooms', withName(name));

export const joinRoom = (roomId: string, name: string) =>
    request<RoomSession>(`/api/rooms/${roomId}/join`, withName(name));

export const getRoom = (roomId: string) => request<RoomSummary>(`/api/rooms/${roomId}`);
