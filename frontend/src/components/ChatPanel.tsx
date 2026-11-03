import { useEffect, useRef, useState, type FormEvent } from 'react';
import type { ChatMessage, Player } from '../types/game';
import { PLAYER_COLORS } from '../utils/labels';

const MAX_LENGTH = 200;

interface ChatPanelProps {
    messages: ChatMessage[];
    players: Player[];
    onSend: (text: string) => void;
}

export const ChatPanel = ({ messages, players, onSend }: ChatPanelProps) => {
    const [text, setText] = useState('');
    const list = useRef<HTMLOListElement>(null);

    useEffect(() => {
        list.current?.scrollTo({ top: list.current.scrollHeight });
    }, [messages]);

    const submit = (event: FormEvent) => {
        event.preventDefault();
        if (!text.trim()) return;
        onSend(text);
        setText('');
    };

    return (
        <section className="panel chat" aria-label="Chat">
            <h2>Chat</h2>
            <ol ref={list}>
                {messages.map((message, index) => (
                    <li key={index}>
                        <span className="swatch small" style={{ background: PLAYER_COLORS[players[message.seat].color] }} />
                        <strong>{players[message.seat].name}</strong>{' '}
                        {message.text}
                    </li>
                ))}
            </ol>
            <form onSubmit={submit}>
                <input
                    aria-label="Message"
                    maxLength={MAX_LENGTH}
                    placeholder="Say something…"
                    value={text}
                    onChange={(event) => setText(event.target.value)}
                />
            </form>
        </section>
    );
};
