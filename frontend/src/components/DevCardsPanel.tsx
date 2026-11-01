import { useState } from 'react';
import { RESOURCES, type DevCard, type Resource } from '../types/game';
import type { SendAction } from '../net/useRoom';
import { DEV_CARD_HELP, DEV_CARD_LABELS, RESOURCE_LABELS } from '../utils/labels';

interface DevCardsPanelProps {
    cards: DevCard[];
    playable: DevCard[];
    canBuy: boolean;
    deckCount: number;
    send: SendAction;
}

const ACTIONS: Partial<Record<DevCard, string>> = {
    knight: 'play_knight',
    road_building: 'play_road_building',
};

const ResourceSelect = ({ label, value, onChange }: {
    label: string;
    value: Resource;
    onChange: (resource: Resource) => void;
}) => (
    <label>
        {label}
        <select value={value} onChange={(event) => onChange(event.target.value as Resource)}>
            {RESOURCES.map((resource) => (
                <option key={resource} value={resource}>{RESOURCE_LABELS[resource]}</option>
            ))}
        </select>
    </label>
);

export const DevCardsPanel = ({ cards, playable, canBuy, deckCount, send }: DevCardsPanelProps) => {
    const [choosing, setChoosing] = useState<DevCard | null>(null);
    const [first, setFirst] = useState<Resource>('wood');
    const [second, setSecond] = useState<Resource>('ore');

    const counts = new Map<DevCard, number>();
    cards.forEach((card) => counts.set(card, (counts.get(card) ?? 0) + 1));

    const play = (card: DevCard) => {
        const action = ACTIONS[card];
        if (action) send(action);
        else setChoosing(card);
    };

    const confirm = () => {
        if (choosing === 'monopoly') send('play_monopoly', { resource: first });
        else send('play_year_of_plenty', { first, second });
        setChoosing(null);
    };

    return (
        <section className="panel" aria-label="Development cards">
            <h2>Development cards <span className="muted">({deckCount} left)</span></h2>
            {cards.length === 0 && <p className="muted">You have no cards.</p>}
            <ul className="dev-cards">
                {[...counts].map(([card, count]) => (
                    <li key={card} title={DEV_CARD_HELP[card]}>
                        <span>{DEV_CARD_LABELS[card]}{count > 1 && ` ×${count}`}</span>
                        {playable.includes(card) && (
                            <button aria-label={`Play ${DEV_CARD_LABELS[card]}`} onClick={() => play(card)}>Play</button>
                        )}
                    </li>
                ))}
            </ul>

            {choosing && playable.includes(choosing) && (
                <div className="trade-row">
                    <ResourceSelect
                        label={choosing === 'monopoly' ? 'Take all' : 'First card'}
                        value={first}
                        onChange={setFirst}
                    />
                    {choosing === 'year_of_plenty' && (
                        <ResourceSelect label="Second card" value={second} onChange={setSecond} />
                    )}
                    <button className="primary" onClick={confirm}>Confirm</button>
                </div>
            )}

            {canBuy && (
                <button
                    className="full"
                    title="1 ore, 1 wheat, 1 sheep"
                    onClick={() => send('buy_dev_card')}
                >Buy a card</button>
            )}
        </section>
    );
};
