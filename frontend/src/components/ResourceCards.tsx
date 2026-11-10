import { useEffect, useRef, useState } from 'react';
import { RESOURCES, type Cards, type PrivateState } from '../types/game';
import { RESOURCE_COLORS } from '../utils/hexLayout';
import { ResourceIcon } from './Art';
import { RESOURCE_LABELS } from '../utils/labels';

const CHANGE_VISIBLE_MS = 1800;

export const ResourceCards = ({ resources }: { resources: PrivateState['resources'] }) => {
    const previous = useRef<Cards>(resources);
    const [changes, setChanges] = useState<Cards>({});

    useEffect(() => {
        const next: Cards = {};
        for (const resource of RESOURCES) {
            const change = (resources[resource] ?? 0) - (previous.current[resource] ?? 0);
            if (change !== 0) next[resource] = change;
        }
        previous.current = resources;
        if (Object.keys(next).length === 0) return;

        // Updating here is the point: the badges exist only because the hand changed
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setChanges(next);
        const timer = window.setTimeout(() => setChanges({}), CHANGE_VISIBLE_MS);
        return () => window.clearTimeout(timer);
    }, [resources]);

    return (
        <div className="hand" aria-label="Your cards">
            {RESOURCES.map((resource) => {
                const change = changes[resource];
                return (
                    <div key={resource} className={(resources[resource] ?? 0) > 0 ? 'card-pile' : 'card-pile empty'}>
                        <span className="card-art" style={{ background: RESOURCE_COLORS[resource] }}>
                            <ResourceIcon resource={resource} size={32} />
                        </span>
                        <strong data-resource={resource}>{resources[resource] ?? 0}</strong>
                        <span>{RESOURCE_LABELS[resource]}</span>
                        {change !== undefined && (
                            <em className={change > 0 ? 'change gain' : 'change loss'}>
                                {change > 0 ? `+${change}` : change}
                            </em>
                        )}
                    </div>
                );
            })}
        </div>
    );
};
