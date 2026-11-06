import { useState } from 'react';
import type { RoomConnection } from '../net/useRoom';
import type { BotLevel, PublicState } from '../types/game';
import { SettingsPanel } from './SettingsPanel';
import { botLabel, BOT_LEVEL_LABELS, BOT_LEVELS } from '../utils/bots';

const MIN_PLAYERS = 2;
const MAX_PLAYERS = 4;

interface LobbyScreenProps {
    state: PublicState;
    seat: number;
    room: RoomConnection;
}

export const LobbyScreen = ({ state, seat, room }: LobbyScreenProps) => {
    const [copied, setCopied] = useState(false);
    const isHost = state.host_seat === seat;
    const link = window.location.href;

    const copyLink = async () => {
        await navigator.clipboard.writeText(link);
        setCopied(true);
    };

    return (
        <main className="center-page">
            <div className="card">
                <h1>Lobby</h1>
                <label>
                    Invite link
                    <div className="invite">
                        <input readOnly value={link} onFocus={(event) => event.target.select()} />
                        <button type="button" onClick={copyLink}>{copied ? 'Copied' : 'Copy'}</button>
                    </div>
                </label>

                <ul className="lobby-players">
                    {state.players.map((player) => (
                        <li key={player.seat}>
                            {/* Bots only connect once the game starts, but they are always ready */}
                            {player.is_bot
                                ? <span className="dot bot" title="Bot, always ready" />
                                : <span className={room.online.includes(player.seat) ? 'dot online' : 'dot'} />}
                            {player.name}
                            {player.seat === state.host_seat && <span className="muted"> · host</span>}
                            {player.seat === seat && <span className="muted"> · you</span>}
                            {player.is_bot && !isHost && <span className="muted"> · {botLabel(player.bot_level)}</span>}
                            {player.is_bot && isHost && (
                                <>
                                    <span className="muted"> · bot</span>
                                    <select
                                        className="bot-level"
                                        aria-label={`Level of ${player.name}`}
                                        value={player.bot_level ?? 'medium'}
                                        onChange={(event) => room.send('set_bot_level', {
                                            seat: player.seat,
                                            level: event.target.value as BotLevel,
                                        })}
                                    >
                                        {BOT_LEVELS.map((level) => (
                                            <option key={level} value={level}>{BOT_LEVEL_LABELS[level]}</option>
                                        ))}
                                    </select>
                                </>
                            )}
                            {isHost && player.is_bot && player.seat === state.players.length - 1 && (
                                <button
                                    className="link"
                                    aria-label={`Remove ${player.name}`}
                                    onClick={() => room.send('remove_bot', { seat: player.seat })}
                                >Remove</button>
                            )}
                        </li>
                    ))}
                </ul>

                {isHost && state.players.length < MAX_PLAYERS && (
                    <button onClick={() => room.send('add_bot')}>Add a bot</button>
                )}

                <SettingsPanel settings={state.settings} editable={isHost} send={room.send} />

                {isHost ? (
                    <button
                        className="primary"
                        disabled={state.players.length < MIN_PLAYERS}
                        onClick={() => room.send('start_game')}
                    >
                        {state.players.length < MIN_PLAYERS ? 'Waiting for players…' : 'Start game'}
                    </button>
                ) : (
                    <p className="muted">Waiting for the host to start the game…</p>
                )}
                {room.error && <p className="form-error" role="alert">{room.error}</p>}
            </div>
        </main>
    );
};
