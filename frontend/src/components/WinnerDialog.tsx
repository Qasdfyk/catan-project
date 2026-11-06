import { useState } from 'react';
import { Link } from 'react-router-dom';
import type { Player } from '../types/game';
import { PLAYER_COLORS } from '../utils/labels';
import { awaitingRematch } from '../utils/rematch';

interface WinnerDialogProps {
    winner: Player;
    players: Player[];
    isHost: boolean;
    /** The host opened the new room and this player is on the way there. */
    rematchStarted: boolean;
    rematchError: string;
    /** The last action the server refused, while it is on screen. */
    actionError: string | null;
    onRematch: () => void;
    onClose: () => void;
}

export const WinnerDialog = ({
    winner, players, isHost, rematchStarted, rematchError, actionError, onRematch, onClose,
}: WinnerDialogProps) => {
    // The error on screen when the host asked; undefined until they do
    const [errorWhenRequested, setErrorWhenRequested] = useState<string | null | undefined>(undefined);
    const requested = awaitingRematch(errorWhenRequested, actionError);
    // Once answered, forget the request, so the same error coming back later can't block the button
    if (errorWhenRequested !== undefined && !requested) setErrorWhenRequested(undefined);
    const ranking = [...players].sort((a, b) => b.victory_points - a.victory_points);

    const rematch = () => {
        setErrorWhenRequested(actionError);
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
                {rematchError || actionError ? (
                    <p className="form-error" role="alert">{rematchError || actionError}</p>
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
