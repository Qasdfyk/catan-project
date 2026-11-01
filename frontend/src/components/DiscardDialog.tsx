import { useState } from 'react';
import type { Cards, PrivateState } from '../types/game';
import type { SendAction } from '../net/useRoom';
import { CardPicker } from './CardPicker';
import { countCards } from '../utils/labels';

interface DiscardDialogProps {
    required: number;
    resources: PrivateState['resources'];
    send: SendAction;
}

export const DiscardDialog = ({ required, resources, send }: DiscardDialogProps) => {
    const [chosen, setChosen] = useState<Cards>({});
    const total = countCards(chosen);

    return (
        <section className="panel notice" aria-label="Discard cards">
            <h2>Discard {required} cards</h2>
            <p className="muted">A 7 was rolled and you hold more than 7 cards.</p>
            <CardPicker
                label="Discard"
                cards={chosen}
                limits={resources}
                maxTotal={required}
                onChange={setChosen}
            />
            <button className="primary" disabled={total !== required} onClick={() => send('discard', { cards: chosen })}>
                Discard ({total}/{required})
            </button>
        </section>
    );
};
