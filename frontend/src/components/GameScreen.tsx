import { useMemo, useState } from 'react';
import type { RoomConnection } from '../net/useRoom';
import type { GameView, LegalMoves, Player, Position, PrivateState, PublicState } from '../types/game';
import { Board, type BoardTargets } from './Board';
import { DiscardDialog } from './DiscardDialog';
import { ResourceCards } from './ResourceCards';
import { TradePanel } from './TradePanel';
import { PLAYER_COLORS } from '../utils/labels';

type BuildMode = 'settlement' | 'road' | 'city' | null;

const NO_TARGETS: BoardTargets = { settlements: [], roads: [], cities: [], robberHexes: [] };

const EMPTY_LEGAL: LegalMoves = {
    settlements: [],
    roads: [],
    cities: [],
    robber_hexes: [],
    steal_targets: [],
    must_discard: 0,
};

interface GameScreenProps {
    state: PublicState;
    mine: PrivateState;
    room: RoomConnection;
}

const instruction = (game: GameView, current: Player, isMyTurn: boolean, mustDiscard: number): string => {
    if (mustDiscard > 0) return `Discard ${mustDiscard} cards.`;
    if (game.turn_phase === 'discard') return 'Waiting for players to discard…';

    if (!isMyTurn) {
        const doing = game.turn_phase === 'setup' ? 'is placing pieces' : 'is playing';
        return `${current.name} ${doing}…`;
    }

    switch (game.turn_phase) {
        case 'setup':
            return game.setup_waiting_for_road
                ? 'Place a road next to your new settlement.'
                : 'Place a settlement.';
        case 'roll_dice':
            return 'Roll the dice.';
        case 'move_robber':
            return 'Move the robber to another tile.';
        case 'steal':
            return 'Choose a player to steal from.';
        default:
            return 'Build, trade or end your turn.';
    }
};

export const GameScreen = ({ state, mine, room }: GameScreenProps) => {
    const game = state.game as GameView;
    const players = state.players as Player[];
    const { send } = room;

    const [buildMode, setBuildMode] = useState<BuildMode>(null);

    const legal = mine.legal ?? EMPTY_LEGAL;
    const current = players[game.current_seat];
    const isMyTurn = game.current_seat === mine.seat && !game.is_game_over;
    const inMain = game.turn_phase === 'main_phase';
    const winner = game.winner_seat === null ? null : players[game.winner_seat];

    const targets = useMemo<BoardTargets>(() => {
        if (!isMyTurn) return NO_TARGETS;
        switch (game.turn_phase) {
            case 'setup':
                return { ...NO_TARGETS, settlements: legal.settlements, roads: legal.roads };
            case 'move_robber':
                return { ...NO_TARGETS, robberHexes: legal.robber_hexes };
            case 'main_phase':
                return {
                    ...NO_TARGETS,
                    settlements: buildMode === 'settlement' ? legal.settlements : [],
                    roads: buildMode === 'road' ? legal.roads : [],
                    cities: buildMode === 'city' ? legal.cities : [],
                };
            default:
                return NO_TARGETS;
        }
    }, [isMyTurn, game.turn_phase, legal, buildMode]);

    const build = (action: string, position: Position) => {
        send(action, { hex: position.hex, direction: position.direction });
        setBuildMode(null);
    };

    const toggleMode = (mode: BuildMode) => setBuildMode(buildMode === mode ? null : mode);

    return (
        <div className="game">
            <header className="topbar">
                <strong>Catan</strong>
                <span className="status-text" data-testid="instruction">
                    {winner
                        ? `${winner.name} won the game!`
                        : instruction(game, current, isMyTurn, legal.must_discard)}
                </span>
                {game.dice_roll !== null && (
                    <span className="dice" data-testid="dice">Rolled {game.dice_roll}</span>
                )}
                {!room.connected && <span className="offline">Reconnecting…</span>}
            </header>

            {room.error && <div className="toast" role="alert">{room.error}</div>}

            <div className="board-area">
                <Board
                    game={game}
                    players={players}
                    targets={targets}
                    onSettlement={(position) => build('build_settlement', position)}
                    onRoad={(position) => build('build_road', position)}
                    onCity={(position) => build('upgrade_city', position)}
                    onRobber={(hex) => send('move_robber', { hex })}
                />
            </div>

            <aside className="side">
                <section className="panel" aria-label="Players">
                    <h2>Players</h2>
                    {players.map((player) => (
                        <div
                            key={player.seat}
                            className={player.seat === game.current_seat ? 'player active' : 'player'}
                        >
                            <span className="swatch" style={{ background: PLAYER_COLORS[player.color] }} />
                            <span className={room.online.includes(player.seat) ? 'dot online' : 'dot'} title="Connection" />
                            <span className="player-name">
                                {player.name}
                                {player.seat === mine.seat && <span className="muted"> (you)</span>}
                            </span>
                            <span className="player-stats">
                                <span title="Cards">{player.card_count} {player.card_count === 1 ? 'card' : 'cards'}</span>
                                <span title="Road length">
                                    road {player.road_length}
                                    {game.longest_road_holder === player.color && ' ★'}
                                </span>
                                <strong title="Victory points" data-testid={`points-${player.seat}`}>
                                    {player.victory_points} VP
                                </strong>
                            </span>
                        </div>
                    ))}
                </section>

                {legal.must_discard > 0 && (
                    <DiscardDialog required={legal.must_discard} resources={mine.resources} send={send} />
                )}

                {legal.steal_targets.length > 0 && (
                    <section className="panel notice" aria-label="Steal">
                        <h2>Steal a card from</h2>
                        <div className="button-row">
                            {legal.steal_targets.map((seat) => (
                                <button key={seat} onClick={() => send('steal', { victim_seat: seat })}>
                                    {players[seat].name}
                                </button>
                            ))}
                        </div>
                    </section>
                )}

                {isMyTurn && game.turn_phase === 'roll_dice' && (
                    <button className="primary big" onClick={() => send('roll_dice')}>Roll dice</button>
                )}

                {isMyTurn && inMain && (
                    <>
                        <section className="panel" aria-label="Build">
                            <h2>Build</h2>
                            <div className="button-row">
                                <button
                                    aria-pressed={buildMode === 'road'}
                                    disabled={legal.roads.length === 0}
                                    title="1 wood, 1 brick"
                                    onClick={() => toggleMode('road')}
                                >Road</button>
                                <button
                                    aria-pressed={buildMode === 'settlement'}
                                    disabled={legal.settlements.length === 0}
                                    title="1 wood, 1 brick, 1 wheat, 1 sheep"
                                    onClick={() => toggleMode('settlement')}
                                >Settlement</button>
                                <button
                                    aria-pressed={buildMode === 'city'}
                                    disabled={legal.cities.length === 0}
                                    title="3 ore, 2 wheat"
                                    onClick={() => toggleMode('city')}
                                >City</button>
                            </div>
                        </section>
                        <TradePanel mine={mine} send={send} />
                        <button className="primary big" onClick={() => { setBuildMode(null); send('end_turn'); }}>
                            End turn
                        </button>
                    </>
                )}

                <section className="panel log" aria-label="Game log">
                    <h2>Log</h2>
                    <ol>
                        {[...game.log].reverse().map((entry, index) => (
                            <li key={game.log.length - index}>{entry}</li>
                        ))}
                    </ol>
                </section>
            </aside>

            <footer className="handbar">
                <ResourceCards resources={mine.resources} />
            </footer>
        </div>
    );
};
