import { useCallback, useEffect, useState, type FormEvent } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import { GameScreen } from '../components/GameScreen';
import { LobbyScreen } from '../components/LobbyScreen';
import { getRoom, joinRematch, joinRoom } from '../net/api';
import { clearSession, loadSession, saveSession } from '../net/session';
import { useRoom } from '../net/useRoom';
import type { RoomSession, RoomSummary } from '../types/game';

export const RoomPage = () => {
    const { roomId = '' } = useParams();
    // A rematch moves to another room on the same route, which must start from a fresh state
    return <Room key={roomId} roomId={roomId} />;
};

const Room = ({ roomId }: { roomId: string }) => {
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
    const navigate = useNavigate();
    const [rematchError, setRematchError] = useState('');
    const rematchRoomId = room.publicState?.rematch_room_id ?? null;

    useEffect(() => {
        if (room.sessionLost) onSessionLost();
    }, [room.sessionLost, onSessionLost]);

    // Every player follows the host into the new room, keeping their seat
    useEffect(() => {
        if (!rematchRoomId) return;
        let cancelled = false;
        joinRematch(session.room_id, session.token)
            .then((joined) => {
                if (cancelled) return;
                saveSession(joined);
                navigate(`/game/${joined.room_id}`);
            })
            .catch((err: Error) => {
                if (!cancelled) setRematchError(err.message);
            });
        return () => { cancelled = true; };
    }, [rematchRoomId, session, navigate]);

    if (!room.publicState || !room.privateState) {
        return <main className="center-page"><p className="muted">Connecting…</p></main>;
    }

    if (room.publicState.status === 'lobby') {
        return <LobbyScreen state={room.publicState} seat={session.seat} room={room} />;
    }
    return (
        <GameScreen
            state={room.publicState}
            mine={room.privateState}
            room={room}
            rematchError={rematchError}
        />
    );
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
