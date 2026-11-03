import { useState } from 'react';
import { RESOURCES, type GameView, type PrivateState, type Resource } from '../types/game';
import type { SendAction } from '../net/useRoom';
import { RESOURCE_LABELS } from '../utils/labels';

interface TradePanelProps {
    mine: PrivateState;
    bank: GameView['bank'];
    send: SendAction;
}

export const TradePanel = ({ mine, bank, send }: TradePanelProps) => {
    const [give, setGive] = useState<Resource>('wood');
    const [get, setGet] = useState<Resource>('ore');
    const rate = mine.trade_rates?.[give] ?? 4;
    const canTrade = give !== get && (mine.resources[give] ?? 0) >= rate && bank[get] > 0;

    return (
        <section className="panel" aria-label="Trade with the bank">
            <h2>Bank trade</h2>
            <div className="trade-row">
                <label>
                    Give {rate}
                    <select value={give} onChange={(event) => setGive(event.target.value as Resource)}>
                        {RESOURCES.map((resource) => (
                            <option key={resource} value={resource}>
                                {RESOURCE_LABELS[resource]} ({mine.trade_rates?.[resource] ?? 4}:1)
                            </option>
                        ))}
                    </select>
                </label>
                <label>
                    Get 1
                    <select value={get} onChange={(event) => setGet(event.target.value as Resource)}>
                        {RESOURCES.map((resource) => (
                            <option key={resource} value={resource}>
                                {RESOURCE_LABELS[resource]} ({bank[resource]} left)
                            </option>
                        ))}
                    </select>
                </label>
            </div>
            <button disabled={!canTrade} onClick={() => send('trade_with_bank', { give, get })}>Trade</button>
        </section>
    );
};
