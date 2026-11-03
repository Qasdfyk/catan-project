import { useState } from 'react';
import type { Cards, Player, PrivateState, TradeOffer } from '../types/game';
import type { SendAction } from '../net/useRoom';
import { CardPicker } from './CardPicker';
import { countCards } from '../utils/labels';

const describe = (cards: Cards) =>
    Object.entries(cards).map(([resource, amount]) => `${amount} ${resource}`).join(', ');

interface PlayerTradePanelProps {
    mine: PrivateState;
    send: SendAction;
}

export const PlayerTradePanel = ({ mine, send }: PlayerTradePanelProps) => {
    const [open, setOpen] = useState(false);
    const [give, setGive] = useState<Cards>({});
    const [get, setGet] = useState<Cards>({});

    const offer = () => {
        send('offer_trade', { give, get });
        setOpen(false);
        setGive({});
        setGet({});
    };

    if (!open) return <button onClick={() => setOpen(true)}>Trade with players</button>;

    return (
        <section className="panel" aria-label="Offer a trade">
            <h2>You give</h2>
            <CardPicker label="Give" cards={give} limits={mine.resources} onChange={setGive} />
            <h2>You get</h2>
            <CardPicker label="Get" cards={get} onChange={setGet} />
            <div className="button-row">
                <button onClick={() => setOpen(false)}>Cancel</button>
                <button
                    className="primary"
                    disabled={countCards(give) === 0 || countCards(get) === 0}
                    onClick={offer}
                >Offer</button>
            </div>
        </section>
    );
};

interface TradeOfferPanelProps {
    offer: TradeOffer;
    players: Player[];
    mine: PrivateState;
    send: SendAction;
}

export const TradeOfferPanel = ({ offer, players, mine, send }: TradeOfferPanelProps) => {
    const proposer = players[offer.proposer_seat];
    const isMine = offer.proposer_seat === mine.seat;
    const accepted = offer.accepted_seats.includes(mine.seat);
    const declined = offer.declined_seats.includes(mine.seat);
    const canPay = Object.entries(offer.get).every(
        ([resource, amount]) => (mine.resources[resource as keyof Cards] ?? 0) >= (amount ?? 0),
    );

    return (
        <section className="panel notice" aria-label="Trade offer">
            <h2>{isMine ? 'Your offer' : `Offer from ${proposer.name}`}</h2>
            <p className="offer-terms">
                {isMine ? 'You give' : 'You get'} <strong>{describe(offer.give)}</strong>
                <br />
                {isMine ? 'You get' : 'You give'} <strong>{describe(offer.get)}</strong>
            </p>

            {isMine ? (
                <>
                    {offer.accepted_seats.length === 0 && (
                        <p className="muted">
                            {offer.declined_seats.length === players.length - 1
                                ? 'Everyone declined.'
                                : 'Waiting for answers…'}
                        </p>
                    )}
                    <div className="button-row">
                        {offer.accepted_seats.map((seat) => (
                            <button
                                key={seat}
                                className="primary"
                                onClick={() => send('confirm_trade', { partner_seat: seat })}
                            >Trade with {players[seat].name}</button>
                        ))}
                        <button onClick={() => send('cancel_trade')}>Withdraw</button>
                    </div>
                </>
            ) : (
                <div className="button-row">
                    <button
                        aria-pressed={accepted}
                        disabled={!canPay}
                        onClick={() => send('respond_trade', { accept: true })}
                    >Accept</button>
                    <button aria-pressed={declined} onClick={() => send('respond_trade', { accept: false })}>
                        Decline
                    </button>
                </div>
            )}
        </section>
    );
};
