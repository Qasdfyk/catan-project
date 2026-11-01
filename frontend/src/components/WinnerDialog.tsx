import { Link } from 'react-router-dom';
import type { Player } from '../types/game';
import { PLAYER_COLORS } from '../utils/labels';

interface WinnerDialogProps {
    winner: Player;
    players: Player[];
    onClose: () => void;
}

export const WinnerDialog = ({ winner, players, onClose }: WinnerDialogProps) => {
    const ranking = [...players].sort((a, b) => b.victory_points - a.victory_points);

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
                <div className="button-row">
                    <button onClick={onClose}>See the board</button>
                    <Link className="button primary" to="/">New game</Link>
                </div>
            </div>
        </div>
    );
};
