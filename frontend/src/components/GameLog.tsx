import type { Player } from '../types/game';
import { LOG_ICONS, logKind, splitNames } from '../utils/gameLog';
import { PLAYER_TEXT_COLORS } from '../utils/labels';

interface GameLogProps {
    log: string[];
    players: Player[];
}

/** The game's events, newest first, with an icon for each kind and the players in their colours. */
export const GameLog = ({ log, players }: GameLogProps) => (
    <section className="panel log" aria-label="Game log">
        <h2>Log</h2>
        <ol>
            {[...log].reverse().map((entry, index) => {
                const kind = logKind(entry);
                const icon = LOG_ICONS[kind];
                return (
                    <li key={log.length - index} className={`log-${kind}`}>
                        <span className="log-icon" title={icon.label} aria-hidden="true">{icon.glyph}</span>
                        <span>
                            {splitNames(entry, players).map((part, partIndex) => part.player ? (
                                <strong
                                    key={partIndex}
                                    className="log-player"
                                    style={{ color: PLAYER_TEXT_COLORS[part.player.color] }}
                                >{part.text}</strong>
                            ) : part.text)}
                        </span>
                    </li>
                );
            })}
        </ol>
    </section>
);
