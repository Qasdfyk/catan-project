import { useEffect, useMemo, useState } from 'react';
import type { RoomConnection } from '../net/useRoom';
import type { GameView, LegalMoves, Player, Position, PrivateState, PublicState } from '../types/game';
import { Board, type BoardTargets } from './Board';
import { ChatPanel } from './ChatPanel';
import { CostDots } from './CostDots';
import { Dice } from './Dice';
import { DevCardsPanel } from './DevCardsPanel';
import { DiscardDialog } from './DiscardDialog';
import { PlayerTradePanel, TradeOfferPanel } from './PlayerTrade';
import { ResourceCards } from './ResourceCards';
import { CardGainBadge, RollGains } from './RollGains';
import { TradePanel } from './TradePanel';
import { TurnTimer } from './TurnTimer';
import { WinnerDialog } from './WinnerDialog';
import { botLabel } from '../utils/bots';
import { PLAYER_COLORS } from '../utils/labels';
import { settingsSummary } from '../utils/settings';
import { useChanges } from '../utils/useChanges';

type BuildMode = 'settlement' | 'road' | 'city' | null;

const ROAD_COST = { wood: 1, brick: 1 };
const SETTLEMENT_COST = { wood: 1, brick: 1, wheat: 1, sheep: 1 };
const CITY_COST = { ore: 3, wheat: 2 };

const NO_TARGETS: BoardTargets = { settlements: [], roads: [], cities: [], robberHexes: [] };

const EMPTY_LEGAL: LegalMoves = {
    settlements: [],
    roads: [],
    cities: [],
    robber_hexes: [],
    steal_targets: [],
    must_discard: 0,
    can_buy_dev_card: false,
    playable_dev_cards: [],
};

interface GameScreenProps {
    state: PublicState;
    mine: PrivateState;
    room: RoomConnection;
    /** Why following the host into the rematch failed, if it did. */
    rematchError: string;
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
        case 'road_building':
            return `Place a free road (${game.free_roads_left} left).`;
        default:
            return 'Build, trade or end your turn.';
    }
};

export const GameScreen = ({ state, mine, room, rematchError }: GameScreenProps) => {
    const game = state.game as GameView;
    const players = state.players as Player[];
    const { send } = room;

    const [buildMode, setBuildMode] = useState<BuildMode>(null);
    const [winnerClosed, setWinnerClosed] = useState(false);
    const changes = useChanges(state, mine.resources);

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
            case 'road_building':
                return { ...NO_TARGETS, roads: legal.roads };
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

    const canRoll = isMyTurn && game.turn_phase === 'roll_dice';
    const canEndTurn = isMyTurn && inMain;

    useEffect(() => {
        document.title = isMyTurn ? 'Your turn · Catan' : 'Catan';
        return () => { document.title = 'Catan'; };
    }, [isMyTurn]);

    useEffect(() => {
        const handleKey = (event: KeyboardEvent) => {
            const target = event.target as HTMLElement;
            if (['INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName)) return;

            if (event.key === 'Escape') setBuildMode(null);
            if (event.key === 'r' && canRoll) send('roll_dice');
            if (event.key === 'e' && canEndTurn) {
                setBuildMode(null);
                send('end_turn');
            }
        };
        window.addEventListener('keydown', handleKey);
        return () => window.removeEventListener('keydown', handleKey);
    }, [canRoll, canEndTurn, send]);

    return (
        <div className={isMyTurn ? 'game my-turn' : 'game'}>
            {winner && (!winnerClosed || rematchError) && (
                <WinnerDialog
                    winner={winner}
                    players={players}
                    isHost={state.host_seat === mine.seat}
                    rematchStarted={state.rematch_room_id !== null}
                    rematchError={rematchError}
                    onRematch={() => send('rematch')}
                    onClose={() => setWinnerClosed(true)}
                />
            )}

            <header className="topbar">
                <strong>Catan</strong>
                <span className="status-text" data-testid="instruction">
                    {winner
                        ? `${winner.name} won the game!`
                        : instruction(game, current, isMyTurn, legal.must_discard)}
                </span>
                {state.turn_deadline !== null && (
                    <TurnTimer
                        key={`${state.turn_deadline}:${state.server_time}`}
                        deadline={state.turn_deadline}
                        serverTime={state.server_time}
                    />
                )}
                {(mine.hidden_points ?? 0) > 0 && (
                    <span className="muted" title="Your hidden Victory Point cards">
                        +{mine.hidden_points} hidden VP
                    </span>
                )}
                {game.dice_roll !== null && game.dice.length === 2 && (
                    <Dice key={changes.rollCount} values={game.dice} total={game.dice_roll} rolling={changes.roll !== null} />
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
                    producing={changes.roll?.producing ?? []}
                    recent={changes.built}
                />
            </div>

            <aside className="side">
                <section className="panel" aria-label="Players">
                    <h2>Players</h2>
                    <p className="muted rules" title="Rules of this game">{settingsSummary(state.settings)}</p>
                    {players.map((player) => (
                        <div
                            key={player.seat}
                            className={player.seat === game.current_seat ? 'player active' : 'player'}
                        >
                            <span className="swatch" style={{ background: PLAYER_COLORS[player.color] }} />
                            <span className={room.online.includes(player.seat) ? 'dot online' : 'dot'} title="Connection" />
                            <span className="player-main">
                                <span className="player-name">
                                    {player.name}
                                    {player.seat === mine.seat && <span className="muted"> (you)</span>}
                                    {player.is_bot && <span className="muted"> ({botLabel(player.bot_level)})</span>}
                                    {!player.is_bot && !room.online.includes(player.seat) && !game.is_game_over && (
                                        <button
                                            className="link"
                                            aria-label={`Let a bot play for ${player.name}`}
                                            onClick={() => send('replace_with_bot', { seat: player.seat })}
                                        >Let a bot play</button>
                                    )}
                                </span>
                                <span className="player-stats">
                                    <span title="Resource cards">{player.card_count} {player.card_count === 1 ? 'card' : 'cards'}<CardGainBadge key={changes.rollCount} gain={changes.roll?.cardGains[player.seat]} /></span>
                                    <span title="Development cards">{player.dev_card_count} dev</span>
                                    <span title="Road length">
                                        road {player.road_length}
                                        {game.longest_road_holder === player.color && ' ★'}
                                    </span>
                                    <span title="Knights played">
                                        army {player.knights_played}
                                        {game.largest_army_holder === player.color && ' ★'}
                                    </span>
                                </span>
                            </span>
                            <strong className="points" title="Victory points" data-testid={`points-${player.seat}`}>
                                {player.victory_points} VP
                            </strong>
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

                {game.trade_offer && (
                    <TradeOfferPanel
                        offer={game.trade_offer}
                        players={players}
                        mine={mine}
                        send={send}
                    />
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
                                >Road <CostDots cost={ROAD_COST} /></button>
                                <button
                                    aria-pressed={buildMode === 'settlement'}
                                    disabled={legal.settlements.length === 0}
                                    title="1 wood, 1 brick, 1 wheat, 1 sheep"
                                    onClick={() => toggleMode('settlement')}
                                >Settlement <CostDots cost={SETTLEMENT_COST} /></button>
                                <button
                                    aria-pressed={buildMode === 'city'}
                                    disabled={legal.cities.length === 0}
                                    title="3 ore, 2 wheat"
                                    onClick={() => toggleMode('city')}
                                >City <CostDots cost={CITY_COST} /></button>
                            </div>
                        </section>
                        <TradePanel mine={mine} bank={game.bank} send={send} />
                        {!game.trade_offer && <PlayerTradePanel mine={mine} send={send} />}
                    </>
                )}

                <DevCardsPanel
                    cards={mine.dev_cards ?? []}
                    playable={legal.playable_dev_cards}
                    canBuy={legal.can_buy_dev_card}
                    deckCount={game.dev_deck_count}
                    send={send}
                />

                <ChatPanel messages={room.chat} players={players} onSend={room.sendChat} />

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
                {changes.roll && <RollGains key={changes.rollCount} gains={changes.roll.ownGains} />}
                {canRoll && (
                    <button className="primary big" title="Shortcut: R" onClick={() => send('roll_dice')}>
                        Roll dice
                    </button>
                )}
                {canEndTurn && (
                    <button
                        className="primary big"
                        title="Shortcut: E"
                        onClick={() => { setBuildMode(null); send('end_turn'); }}
                    >End turn</button>
                )}
            </footer>
        </div>
    );
};
