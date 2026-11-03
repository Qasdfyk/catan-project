import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useParams } from 'react-router-dom';
import { GameScreen } from '../components/GameScreen';
import { LobbyScreen } from '../components/LobbyScreen';
import { getRoom, joinRoom } from '../net/api';
import { clearSession, loadSession, saveSession } from '../net/session';
import { useRoom } from '../net/useRoom';
import type { RoomSession, RoomSummary } from '../types/game';

export const RoomPage = () => {
    const { roomId = '' } = useParams();
    const [session, setSession] = useState<RoomSession | null>(() => loadSession(roomId));

    const handleJoined = useCallback((joined: RoomSession) => {
        saveSession(joined);
        setSession(joined);
    }, []);

    const handleSessionLost = useCallback(() => {
        clearSession(roomId);
        setSession(null);
    }, [roomId]);

    if (!session) return <JoinForm roomId={roomId} onJoined={handleJoined} />;
    return <ConnectedRoom key={session.token} session={session} onSessionLost={handleSessionLost} />;
};

interface ConnectedRoomProps {
    session: RoomSession;
    onSessionLost: () => void;
}

const ConnectedRoom = ({ session, onSessionLost }: ConnectedRoomProps) => {
    const room = useRoom(session);

    useEffect(() => {
        if (room.sessionLost) onSessionLost();
    }, [room.sessionLost, onSessionLost]);

    if (!room.publicState || !room.privateState) {
        return <main className="center-page"><p className="muted">Connecting…</p></main>;
    }

    if (room.publicState.status === 'lobby') {
        return <LobbyScreen state={room.publicState} seat={session.seat} room={room} />;
    }
    return <GameScreen state={room.publicState} mine={room.privateState} room={room} />;
};

interface JoinFormProps {
    roomId: string;
    onJoined: (session: RoomSession) => void;
}

const JoinForm = ({ roomId, onJoined }: JoinFormProps) => {
    const [summary, setSummary] = useState<RoomSummary | null>(null);
    const [loadError, setLoadError] = useState('');
    const [name, setName] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');

    useEffect(() => {
        getRoom(roomId).then(setSummary).catch((err: Error) => setLoadError(err.message));
    }, [roomId]);

    const handleSubmit = async (event: FormEvent) => {
        event.preventDefault();
        setBusy(true);
        setError('');
        try {
            onJoined(await joinRoom(roomId, name));
        } catch (err) {
            setError((err as Error).message);
            setBusy(false);
        }
    };

    if (loadError) {
        return (
            <main className="center-page">
                <div className="card">
                    <h1>Catan</h1>
                    <p className="form-error" role="alert">{loadError}</p>
                    <Link to="/">Create a new room</Link>
                </div>
            </main>
        );
    }

    if (!summary) return <main className="center-page"><p className="muted">Loading…</p></main>;

    const started = summary.status !== 'lobby';
    const waiting = summary.players.filter((player) => !player.online);

    return (
        <main className="center-page">
            <form className="card" onSubmit={handleSubmit}>
                <h1>{started ? 'Return to the game' : 'Join the game'}</h1>
                <p className="muted">
                    Players: {summary.players.map((player) => player.name).join(', ')}
                </p>
                {started && (
                    <p className="muted">
                        {waiting.length > 0
                            ? `Enter your name to take your seat back: ${waiting.map((p) => p.name).join(', ')}.`
                            : 'All players are connected.'}
                    </p>
                )}
                <label>
                    Your name
                    <input
                        autoFocus
                        maxLength={20}
                        value={name}
                        onChange={(event) => setName(event.target.value)}
                    />
                </label>
                <button className="primary" disabled={busy || !name.trim()}>
                    {busy ? 'Joining…' : started ? 'Return' : 'Join'}
                </button>
                {error && <p className="form-error" role="alert">{error}</p>}
            </form>
        </main>
    );
};
