import { useId } from 'react';
import type { DesertPlacement, GameSettings } from '../types/game';
import type { SendAction } from '../net/useRoom';
import {
    DESERT_LABELS,
    DISCARD_LIMIT_OPTIONS,
    sameSettings,
    STANDARD_SETTINGS,
    turnTimerLabel,
    TURN_SECONDS_OPTIONS,
    TWO_PLAYER_SETTINGS,
    VICTORY_POINT_OPTIONS,
} from '../utils/settings';

interface SettingsPanelProps {
    settings: GameSettings;
    /** Only the host may change the rules; everyone else sees them update live. */
    editable: boolean;
    send: SendAction;
}

const PRESETS = [
    { label: 'Standard rules', settings: STANDARD_SETTINGS },
    { label: 'Recommended for 2 players', settings: TWO_PLAYER_SETTINGS },
];

const TIMER_HINT = 'not enforced yet';

export const SettingsPanel = ({ settings, editable, send }: SettingsPanelProps) => {
    const timerHintId = useId();
    const update = (change: Partial<GameSettings>) => send('update_settings', change);

    return (
        <section className="settings" aria-label="Game settings">
            <h2>Rules</h2>
            <div className="chips">
                {PRESETS.map((preset) => (
                    <button
                        key={preset.label}
                        className="chip"
                        aria-pressed={sameSettings(settings, preset.settings)}
                        disabled={!editable}
                        onClick={() => update(preset.settings)}
                    >{preset.label}</button>
                ))}
            </div>

            {editable ? (
                <div className="settings-grid">
                    <label>
                        Points to win
                        <select
                            value={settings.victory_points}
                            onChange={(event) => update({ victory_points: Number(event.target.value) })}
                        >
                            {VICTORY_POINT_OPTIONS.map((points) => (
                                <option key={points} value={points}>{points}</option>
                            ))}
                        </select>
                    </label>
                    <label>
                        Discard on a 7 above
                        <select
                            value={settings.discard_limit}
                            onChange={(event) => update({ discard_limit: Number(event.target.value) })}
                        >
                            {DISCARD_LIMIT_OPTIONS.map((limit) => (
                                <option key={limit} value={limit}>{limit} cards</option>
                            ))}
                        </select>
                    </label>
                    <label>
                        Desert
                        <select
                            value={settings.desert}
                            onChange={(event) => update({ desert: event.target.value as DesertPlacement })}
                        >
                            {Object.entries(DESERT_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                    </label>
                    <label>
                        Turn timer
                        <select
                            value={settings.turn_seconds ?? 'off'}
                            aria-describedby={timerHintId}
                            onChange={(event) => update({
                                turn_seconds: event.target.value === 'off' ? null : Number(event.target.value),
                            })}
                        >
                            {TURN_SECONDS_OPTIONS.map((seconds) => (
                                <option key={seconds ?? 'off'} value={seconds ?? 'off'}>{turnTimerLabel(seconds)}</option>
                            ))}
                        </select>
                        <span id={timerHintId} className="muted hint">{TIMER_HINT}</span>
                    </label>
                    <label className="check">
                        <input
                            type="checkbox"
                            checked={settings.friendly_robber}
                            onChange={(event) => update({ friendly_robber: event.target.checked })}
                        />
                        <span>
                            Friendly robber
                            <span className="muted hint"> · spares players with 2 points or fewer</span>
                        </span>
                    </label>
                </div>
            ) : (
                <dl className="settings-list">
                    <dt>Points to win</dt>
                    <dd>{settings.victory_points}</dd>
                    <dt>Discard on a 7 above</dt>
                    <dd>{settings.discard_limit} cards</dd>
                    <dt>Desert</dt>
                    <dd>{DESERT_LABELS[settings.desert]}</dd>
                    <dt>Turn timer</dt>
                    <dd>
                        {turnTimerLabel(settings.turn_seconds)}
                        {settings.turn_seconds !== null && <span className="muted hint"> · {TIMER_HINT}</span>}
                    </dd>
                    <dt>Friendly robber</dt>
                    <dd>{settings.friendly_robber ? 'On' : 'Off'}</dd>
                </dl>
            )}
        </section>
    );
};
