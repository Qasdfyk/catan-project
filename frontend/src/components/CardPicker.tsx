import { RESOURCES, type Cards, type Resource } from '../types/game';
import { countCards, RESOURCE_LABELS } from '../utils/labels';

interface CardPickerProps {
    /** Starts the accessible button names, such as "Discard one wood more". */
    label: string;
    cards: Cards;
    /** The most of each resource; without it only `maxTotal` applies. */
    limits?: Cards;
    maxTotal?: number;
    onChange: (cards: Cards) => void;
}

export const CardPicker = ({ label, cards, limits, maxTotal, onChange }: CardPickerProps) => {
    const total = countCards(cards);
    const change = (resource: Resource, delta: number) => {
        onChange({ ...cards, [resource]: (cards[resource] ?? 0) + delta });
    };

    return (
        <div className="discard-rows">
            {RESOURCES.map((resource) => {
                const amount = cards[resource] ?? 0;
                const limit = limits ? limits[resource] ?? 0 : Infinity;
                return (
                    <div key={resource} className="discard-row">
                        <span>{RESOURCE_LABELS[resource]}</span>
                        <button
                            aria-label={`${label} one ${resource} less`}
                            disabled={amount === 0}
                            onClick={() => change(resource, -1)}
                        >−</button>
                        <strong>{amount}</strong>
                        <button
                            aria-label={`${label} one ${resource} more`}
                            disabled={amount >= limit || (maxTotal !== undefined && total >= maxTotal)}
                            onClick={() => change(resource, 1)}
                        >+</button>
                        <span className="muted">{limits ? `of ${limit}` : ''}</span>
                    </div>
                );
            })}
        </div>
    );
};
