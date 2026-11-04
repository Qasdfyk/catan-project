import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Player } from '../types/game';
import { PLAYER_COLORS } from '../utils/labels';

interface WinnerDialogProps {
    winner: Player;
    players: Player[];
    isHost: boolean;
    /** The host opened the new room and this player is on the way there. */
    rematchStarted: boolean;
    rematchError: string;
    onRematch: () => void;
    onClose: () => void;
}

export const WinnerDialog = ({
    winner, players, isHost, rematchStarted, rematchError, onRematch, onClose,
}: WinnerDialogProps) => {
    const [requested, setRequested] = useState(false);
    const ranking = [...players].sort((a, b) => b.victory_points - a.victory_points);

    const rematch = () => {
        setRequested(true);
        onRematch();
    };

    return (
        <div className="overlay">
            <div className="card" role="dialog" aria-label="Game over">
                <h1>{winner.name} won!</h1>
                <ol className="ranking">
                    {ranking.map((player) => (
                        <li key={player.seat}>
                            <span className="swatch" style={{ background: PLAYER_COLORS[player.color] }} />
                            <span className="player-name">{player.name}</span>
                            <strong>{player.victory_points} VP</strong>
                        </li>
                    ))}
                </ol>
                {rematchError ? (
                    <p className="form-error" role="alert">{rematchError}</p>
                ) : rematchStarted ? (
                    <p className="muted">Joining the rematch…</p>
                ) : !isHost && (
                    <p className="muted">Waiting for the host to start a rematch…</p>
                )}
                <div className="button-row">
                    <button onClick={onClose}>See the board</button>
                    {isHost ? (
                        <>
                            <Link className="button" to="/">New game</Link>
                            <button
                                className="primary"
                                disabled={requested || rematchStarted}
                                onClick={rematch}
                            >Rematch</button>
                        </>
                    ) : (
                        <Link className="button primary" to="/">New game</Link>
                    )}
                </div>
            </div>
        </div>
    );
};
