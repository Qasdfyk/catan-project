import { RESOURCES, type PrivateState } from '../types/game';
import { RESOURCE_COLORS } from '../utils/hexLayout';
import { RESOURCE_LABELS } from '../utils/labels';

export const ResourceCards = ({ resources }: { resources: PrivateState['resources'] }) => (
    <div className="hand" aria-label="Your cards">
        {RESOURCES.map((resource) => (
            <div key={resource} className="card-pile" style={{ borderTopColor: RESOURCE_COLORS[resource] }}>
                <strong data-resource={resource}>{resources[resource] ?? 0}</strong>
                <span>{RESOURCE_LABELS[resource]}</span>
            </div>
        ))}
    </div>
);
