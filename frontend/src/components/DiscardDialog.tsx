import { useState } from 'react';
import { RESOURCES, type PrivateState, type Resource } from '../types/game';
import type { SendAction } from '../net/useRoom';
import { RESOURCE_LABELS } from '../utils/labels';

interface DiscardDialogProps {
    required: number;
    resources: PrivateState['resources'];
    send: SendAction;
}

export const DiscardDialog = ({ required, resources, send }: DiscardDialogProps) => {
    const [chosen, setChosen] = useState<Partial<Record<Resource, number>>>({});
    const total = Object.values(chosen).reduce((sum, amount) => sum + (amount ?? 0), 0);

    const change = (resource: Resource, delta: number) => {
        setChosen({ ...chosen, [resource]: (chosen[resource] ?? 0) + delta });
    };

    return (
        <section className="panel notice" aria-label="Discard cards">
            <h2>Discard {required} cards</h2>
            <p className="muted">A 7 was rolled and you hold more than 7 cards.</p>
            <div className="discard-rows">
                {RESOURCES.map((resource) => {
                    const owned = resources[resource] ?? 0;
                    const amount = chosen[resource] ?? 0;
                    return (
                        <div key={resource} className="discard-row">
                            <span>{RESOURCE_LABELS[resource]}</span>
                            <button
                                aria-label={`Discard one ${resource} less`}
                                disabled={amount === 0}
                                onClick={() => change(resource, -1)}
                            >−</button>
                            <strong>{amount}</strong>
                            <button
                                aria-label={`Discard one ${resource} more`}
                                disabled={amount >= owned || total >= required}
                                onClick={() => change(resource, 1)}
                            >+</button>
                            <span className="muted">of {owned}</span>
                        </div>
                    );
                })}
            </div>
            <button className="primary" disabled={total !== required} onClick={() => send('discard', { cards: chosen })}>
                Discard ({total}/{required})
            </button>
        </section>
    );
};
