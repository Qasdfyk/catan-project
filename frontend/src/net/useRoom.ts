import { useCallback, useEffect, useRef, useState } from 'react';
import type { ChatMessage, PrivateState, PublicState, RoomSession } from '../types/game';

const RECONNECT_DELAYS_MS = [500, 1000, 2000, 4000];
const ERROR_VISIBLE_MS = 5000;

const socketUrl = () => {
    const scheme = window.location.protocol === 'https:' ? 'wss' : 'ws';
    return `${scheme}://${window.location.host}/ws`;
};

type ServerMessage =
    | { type: 'state'; public: PublicState; private: PrivateState }
    | { type: 'presence'; online: number[] }
    | ({ type: 'chat' } & ChatMessage)
    | { type: 'ack'; request_id: number }
    | { type: 'error'; message: string; fatal?: boolean };

export type SendAction = (action: string, payload?: Record<string, unknown>) => void;

export interface RoomConnection {
    connected: boolean;
    publicState: PublicState | null;
    privateState: PrivateState | null;
    online: number[];
    error: string | null;
    /** The session is gone (room removed or seat taken over): the player must join again. */
    sessionLost: boolean;
    chat: ChatMessage[];
    send: SendAction;
    sendChat: (text: string) => void;
}

export const useRoom = (session: RoomSession): RoomConnection => {
    const [connected, setConnected] = useState(false);
    const [publicState, setPublicState] = useState<PublicState | null>(null);
    const [privateState, setPrivateState] = useState<PrivateState | null>(null);
    const [online, setOnline] = useState<number[]>([]);
    const [error, setError] = useState<string | null>(null);
    const [sessionLost, setSessionLost] = useState(false);
    const [chat, setChat] = useState<ChatMessage[]>([]);

    const socketRef = useRef<WebSocket | null>(null);
    const requestId = useRef(0);
    const version = useRef(0);
    const errorTimer = useRef<number | undefined>(undefined);

    const showError = useCallback((message: string) => {
        setError(message);
        window.clearTimeout(errorTimer.current);
        errorTimer.current = window.setTimeout(() => setError(null), ERROR_VISIBLE_MS);
    }, []);

    useEffect(() => {
        let closed = false;
        let attempts = 0;
        let retryTimer: number | undefined;

        const connect = () => {
            const socket = new WebSocket(socketUrl());
            socketRef.current = socket;

            socket.onopen = () => {
                // The gateway sends the recent history after every connection
                setChat([]);
                socket.send(JSON.stringify({ type: 'hello', room_id: session.room_id, token: session.token }));
            };

            socket.onmessage = (event) => {
                const message = JSON.parse(event.data) as ServerMessage;
                if (message.type === 'state') {
                    attempts = 0;
                    setConnected(true);
                    // An event can overtake the snapshot sent right after connecting
                    if (message.public.version >= version.current) {
                        version.current = message.public.version;
                        setPublicState(message.public);
                        setPrivateState(message.private);
                    }
                } else if (message.type === 'presence') {
                    setOnline(message.online);
                } else if (message.type === 'chat') {
                    setChat((messages) => [...messages, message]);
                } else if (message.type === 'error') {
                    if (message.fatal) {
                        closed = true;
                        setSessionLost(true);
                    }
                    showError(message.message);
                }
            };

            socket.onclose = () => {
                setConnected(false);
                if (closed) return;
                const delay = RECONNECT_DELAYS_MS[Math.min(attempts, RECONNECT_DELAYS_MS.length - 1)];
                attempts += 1;
                retryTimer = window.setTimeout(connect, delay);
            };
        };

        connect();

        return () => {
            closed = true;
            window.clearTimeout(retryTimer);
            socketRef.current?.close();
        };
    }, [session, showError]);

    const send = useCallback<SendAction>((action, payload = {}) => {
        const socket = socketRef.current;
        if (!socket || socket.readyState !== WebSocket.OPEN) {
            showError('Not connected. Reconnecting…');
            return;
        }
        requestId.current += 1;
        socket.send(JSON.stringify({ type: 'action', request_id: requestId.current, action, payload }));
    }, [showError]);

    const sendChat = useCallback((text: string) => {
        const socket = socketRef.current;
        if (socket?.readyState === WebSocket.OPEN) {
            socket.send(JSON.stringify({ type: 'chat', text }));
        }
    }, []);

    return { connected, publicState, privateState, online, error, sessionLost, chat, send, sendChat };
};
