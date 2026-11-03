import { useState, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { createRoom } from '../net/api';
import { saveSession } from '../net/session';

export const Home = () => {
    const [name, setName] = useState('');
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState('');
    const navigate = useNavigate();

    const handleSubmit = async (event: FormEvent) => {
        event.preventDefault();
        setBusy(true);
        setError('');
        try {
            const session = await createRoom(name);
            saveSession(session);
            navigate(`/game/${session.room_id}`);
        } catch (err) {
            setError((err as Error).message);
            setBusy(false);
        }
    };

    return (
        <main className="center-page">
            <form className="card" onSubmit={handleSubmit}>
                <h1>Catan</h1>
                <p className="muted">Create a room, then invite friends or fill the seats with bots.</p>
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
                    {busy ? 'Creating…' : 'Create room'}
                </button>
                {error && <p className="form-error" role="alert">{error}</p>}
            </form>
        </main>
    );
};
